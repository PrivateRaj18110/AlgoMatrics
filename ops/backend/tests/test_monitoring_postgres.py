"""The monitoring.v1 receiver against a real PostgreSQL database.

The SQLite suite in ``test_monitoring_receiver.py`` proves the receiver's
*logic*. It cannot prove its *behaviour under a real database*, because SQLite
serialises writers, has no MVCC snapshot isolation, does not abort a transaction
on a constraint violation, and accepts type coercions PostgreSQL refuses. Every
test here exists because of a difference SQLite hides.

Skipped in full unless ``MONITORING_PG_URL`` names a PostgreSQL database. It
must be a **staging** database: the suite truncates monitoring tables between
tests and would destroy anything already there.

Concurrency is exercised by calling the receiver from real OS threads. Each
call opens its own session from the same engine, so the writers contend on the
real PostgreSQL constraints rather than on a test double.
"""

from __future__ import annotations

import concurrent.futures as futures
import hashlib
import json
import os
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, text

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO = BACKEND_DIR.parents[1]
PACKAGE = REPO / "tests" / "fixtures" / "lls-monitoring-v1-handoff"
MESSAGES = PACKAGE / "fixtures" / "messages"

PG_URL = os.environ.get("MONITORING_PG_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not PG_URL,
    reason="MONITORING_PG_URL is not set; these tests require a real staging PostgreSQL",
)

SOURCE_ID = "lls-contract-fixture"
PUBLISH_TOKEN = "pg-suite-upload-token"  # noqa: S105 - staging test credential
ADMIN_TOKEN = "pg-suite-admin-token"  # noqa: S105 - staging test credential
DEPLOYMENT = "staging"

MONITORING_TABLES = (
    "monitoring_projections",
    "monitoring_quarantine",
    "monitoring_raw_requests",
    "monitoring_sequence_state",
    "monitoring_audit",
    "monitoring_evidence",
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def _truncate() -> None:
    """Clear monitoring tables between tests.

    ``TRUNCATE``, not ``DELETE``: migration ``c7f41a92d8e5`` blocks row-level
    DELETE on ``monitoring_evidence`` in the database itself. Row triggers do
    not fire for TRUNCATE, which is exactly why it remains available for
    resetting a test database while being useless for quietly editing history.
    """
    engine = create_engine(PG_URL, future=True)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {', '.join(MONITORING_TABLES)}"))
    engine.dispose()


@pytest.fixture
def pg(monkeypatch: pytest.MonkeyPatch):
    """A receiver bound to the staging PostgreSQL database."""
    from app.core.config import get_settings
    from app.database import session as session_module
    from app.monitoring import contract

    monkeypatch.setenv("OPS_DATABASE_URL", PG_URL)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setenv("MONITORING_SOURCE_TOKENS", f"{SOURCE_ID}:{PUBLISH_TOKEN}")
    monkeypatch.setenv("MONITORING_ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.setenv("MONITORING_DEPLOYMENT_ENVIRONMENT", DEPLOYMENT)
    monkeypatch.setenv("MONITORING_SCHEMA_DIR", str(REPO / "schemas" / "monitoring-v1"))

    get_settings.cache_clear()
    session_module._engine = None
    session_module._SessionLocal = None
    contract.reset_cache()

    _truncate()
    yield

    get_settings.cache_clear()
    session_module._engine = None
    session_module._SessionLocal = None


def principal(request_id: str | None = None):
    from app.api.dependencies.monitoring_auth import MonitoringPrincipal

    return MonitoringPrincipal(
        source_id=SOURCE_ID,
        environments=frozenset(),
        request_id=request_id or uuid.uuid4().hex,
        remote_addr="127.0.0.1",
    )


def fixture_bytes(name: str) -> bytes:
    return (MESSAGES / name).read_bytes()


def fixture_doc(name: str) -> dict[str, Any]:
    return json.loads(fixture_bytes(name))


def ingest(name: str, *, body: bytes | None = None, digest: str | None = None):
    from app.monitoring import receiver

    raw = body if body is not None else fixture_bytes(name)
    return receiver.ingest_message(raw, principal(), declared_digest=digest)


def session_for():
    from app.database.session import get_sessionmaker

    return get_sessionmaker()()


def query_scalar(sql: str, **params: Any) -> Any:
    engine = create_engine(PG_URL, future=True)
    try:
        with engine.connect() as connection:
            return connection.execute(text(sql), params).scalar()
    finally:
        engine.dispose()


def query_all(sql: str, **params: Any) -> list[tuple]:
    engine = create_engine(PG_URL, future=True)
    try:
        with engine.connect() as connection:
            return list(connection.execute(text(sql), params).all())
    finally:
        engine.dispose()


# --------------------------------------------------------------------------- #
# Deployed schema
# --------------------------------------------------------------------------- #
def test_monitoring_tables_exist_with_postgres_types(pg: None) -> None:
    """The migration produced real PostgreSQL types, not SQLite's loose ones."""
    rows = dict(
        query_all(
            "select column_name, data_type from information_schema.columns "
            "where table_name = 'monitoring_evidence'"
        )
    )
    assert rows["message_id"] == "character varying"
    assert rows["sequence_ordinal"] == "bigint"
    # timestamptz, not a naive timestamp: an aware value must survive the round
    # trip or every comparison downstream silently shifts.
    assert rows["generated_at"] == "timestamp with time zone"
    assert rows["received_at"] == "timestamp with time zone"
    assert rows["message_json"] == "text"


def test_evidence_primary_key_is_the_content_address(pg: None) -> None:
    """The duplicate guarantee rests on this constraint, not on application logic."""
    constraint = query_scalar(
        "select con.conname from pg_constraint con "
        "join pg_class rel on rel.oid = con.conrelid "
        "where rel.relname = 'monitoring_evidence' and con.contype = 'p'"
    )
    assert constraint == "monitoring_evidence_pkey"


# --------------------------------------------------------------------------- #
# Evidence persistence
# --------------------------------------------------------------------------- #
def test_one_accepted_message_is_one_immutable_evidence_row(pg: None) -> None:
    """Every field of the producer's message survives the PostgreSQL round trip."""
    from app.models.monitoring import MonitoringEvidence
    from app.monitoring import contract

    document = fixture_doc("valid_snapshot.json")
    ack = ingest("valid_snapshot.json")
    assert ack.status == "accepted"

    assert query_scalar("select count(*) from monitoring_evidence") == 1

    session = session_for()
    try:
        row = session.get(MonitoringEvidence, document["message_id"])
        assert row is not None

        # Identity and digest.
        assert row.message_id == document["message_id"]
        assert row.message_id == contract.message_identity(document)
        assert row.request_sha256 == contract.request_digest(fixture_bytes("valid_snapshot.json"))

        # Source identity, with the sequence kept as the producer's string.
        assert row.source_id == document["source_id"]
        assert row.source_instance == document["source_instance"]
        assert row.source_sequence == document["source_sequence"]
        assert isinstance(row.source_sequence, str)
        assert row.sequence_ordinal == int(document["source_sequence"])

        assert row.message_type == document["message_type"]
        assert row.schema_version == document["schema_version"]

        # Two environments, never conflated: the producer said offline_fixture,
        # we are deployed in staging, and both are recorded as themselves.
        assert row.source_environment == document["environment"]
        assert row.receiver_deployment_environment == DEPLOYMENT
        assert row.source_environment != row.receiver_deployment_environment

        # Qualifier objects, verbatim.
        assert json.loads(row.source_as_of_json) == document["source_as_of"]
        assert json.loads(row.coverage_json) == document["coverage"]
        assert json.loads(row.freshness_json) == document["freshness"]
        assert json.loads(row.trust_json) == document["trust"]

        # runtime stays the array it is.
        runtime = json.loads(row.runtime_json)
        assert isinstance(runtime, list)
        assert runtime == document["runtime"]

        assert row.capture_ref == document["payload"]["capture_ref"]

        # The whole message, recoverable byte-for-byte as canonical JSON.
        assert json.loads(row.message_json) == document
        assert row.message_json.encode("utf-8") == contract.canonical_json(document)
    finally:
        session.close()


def test_timestamps_come_back_timezone_aware(pg: None) -> None:
    """PostgreSQL returns aware datetimes; SQLite returns naive ones.

    Code that compared them without normalising would work in the SQLite suite
    and raise in staging, so the round trip is asserted explicitly.
    """
    from app.models.monitoring import MonitoringEvidence

    document = fixture_doc("valid_snapshot.json")
    ingest("valid_snapshot.json")

    session = session_for()
    try:
        row = session.get(MonitoringEvidence, document["message_id"])
        assert row.generated_at.tzinfo is not None
        assert row.received_at.tzinfo is not None
        expected = datetime.fromisoformat(document["generated_at"])
        assert row.generated_at == expected
    finally:
        session.close()


# --------------------------------------------------------------------------- #
# Immutability
# --------------------------------------------------------------------------- #
def test_api_timestamps_are_utc_regardless_of_server_timezone(pg: None) -> None:
    """The rendered timestamp must not depend on where the server runs.

    PostgreSQL returns ``timestamptz`` in the session's time zone, so on a
    deployment in IST this rendered ``...T14:31:34.627414+05:30`` while the
    SQLite suite rendered the same producer instant as ``...T09:01:34.627414Z``.
    Same moment, but a representation the producer never asserted.
    """
    from app.monitoring import views

    document = fixture_doc("valid_snapshot.json")
    ingest("valid_snapshot.json")

    session = session_for()
    try:
        from app.models.monitoring import MonitoringEvidence

        row = session.get(MonitoringEvidence, document["message_id"])
        rendered = views.evidence_view(row)
    finally:
        session.close()

    generated = rendered["time"]["generatedAt"]
    assert generated.endswith("Z"), generated
    assert "+" not in generated, generated
    # And still the producer's instant, not merely a plausible one.
    assert datetime.fromisoformat(generated.replace("Z", "+00:00")) == datetime.fromisoformat(
        document["generated_at"]
    )
    assert rendered["time"]["receivedAt"].endswith("Z")


def test_evidence_update_is_refused_by_the_orm(pg: None) -> None:
    from app.models.monitoring import EvidenceIsImmutable, MonitoringEvidence

    document = fixture_doc("valid_snapshot.json")
    ingest("valid_snapshot.json")

    session = session_for()
    try:
        row = session.get(MonitoringEvidence, document["message_id"])
        row.source_environment = "live_trading"
        with pytest.raises(EvidenceIsImmutable):
            session.flush()
        session.rollback()
    finally:
        session.close()

    # Unchanged on disk.
    assert (
        query_scalar(
            "select source_environment from monitoring_evidence where message_id = :m",
            m=document["message_id"],
        )
        == document["environment"]
    )


def test_evidence_delete_is_refused_by_the_orm(pg: None) -> None:
    from app.models.monitoring import EvidenceIsImmutable, MonitoringEvidence

    document = fixture_doc("valid_snapshot.json")
    ingest("valid_snapshot.json")

    session = session_for()
    try:
        row = session.get(MonitoringEvidence, document["message_id"])
        session.delete(row)
        with pytest.raises(EvidenceIsImmutable):
            session.flush()
        session.rollback()
    finally:
        session.close()

    assert query_scalar("select count(*) from monitoring_evidence") == 1


def test_evidence_is_append_only_below_the_orm_too(pg: None) -> None:
    """The guarantee must survive paths that never touch a mapped object.

    SQLAlchemy Core bulk statements emit no mapper events, so before migration
    ``c7f41a92d8e5`` these rewrote and destroyed evidence with the application's
    own credential. The database now refuses them.
    """
    from app.models.monitoring import MonitoringEvidence
    from sqlalchemy.exc import IntegrityError

    document = fixture_doc("valid_snapshot.json")
    ingest("valid_snapshot.json")

    from sqlalchemy import delete as sa_delete
    from sqlalchemy import update as sa_update

    for statement in (
        sa_update(MonitoringEvidence)
        .where(MonitoringEvidence.message_id == document["message_id"])
        .values(source_environment="live_trading"),
        sa_delete(MonitoringEvidence).where(
            MonitoringEvidence.message_id == document["message_id"]
        ),
    ):
        session = session_for()
        try:
            with pytest.raises(IntegrityError):
                session.execute(statement)
                session.commit()
            session.rollback()
        finally:
            session.close()

    engine = create_engine(PG_URL, future=True)
    try:
        for sql in (
            "UPDATE monitoring_evidence SET source_environment = 'live_trading'",
            "DELETE FROM monitoring_evidence",
        ):
            with pytest.raises(IntegrityError), engine.begin() as connection:
                connection.execute(text(sql))
    finally:
        engine.dispose()

    # Untouched, and still exactly what the producer sent.
    assert query_scalar("select count(*) from monitoring_evidence") == 1
    assert (
        query_scalar("select source_environment from monitoring_evidence")
        == document["environment"]
    )


def test_appending_new_evidence_is_still_permitted(pg: None) -> None:
    """The guard blocks rewriting history, not recording it."""
    assert ingest("valid_snapshot.json").status == "accepted"
    assert ingest("valid_events.json").status == "accepted"
    assert query_scalar("select count(*) from monitoring_evidence") == 2


def test_evidence_hash_is_stable_across_reads(pg: None) -> None:
    """The stored bytes are the evidence; re-reading must not reshape them."""
    import hashlib

    ingest("valid_snapshot.json")
    first = query_scalar("select md5(message_json) from monitoring_evidence")
    second = query_scalar("select md5(message_json) from monitoring_evidence")
    assert first == second

    stored = query_scalar("select message_json from monitoring_evidence")
    from app.monitoring import contract

    assert (
        hashlib.sha256(stored.encode("utf-8")).hexdigest()
        == hashlib.sha256(contract.canonical_json(fixture_doc("valid_snapshot.json"))).hexdigest()
    )


# --------------------------------------------------------------------------- #
# Duplicates — sequential
# --------------------------------------------------------------------------- #
def test_identical_redelivery_is_a_duplicate_not_a_second_row(pg: None) -> None:
    first = ingest("valid_snapshot.json")
    assert first.status == "accepted"

    for _ in range(4):
        again = ingest("valid_snapshot.json")
        assert again.status == "duplicate"
        # The ACK identity must not drift between deliveries.
        assert again.message_id == first.message_id
        assert again.sha256 == first.sha256
        assert again.source_sequence == first.source_sequence

    assert query_scalar("select count(*) from monitoring_evidence") == 1
    assert query_scalar("select count(*) from monitoring_projections") == 1


def test_duplicate_after_later_sequences_is_still_a_duplicate(pg: None) -> None:
    """The contract requires this: duplicate is decided before the ordering rule."""
    first = ingest("order_b_sequence_1.json")
    assert first.status == "accepted"
    assert ingest("order_b_sequence_2.json").status == "accepted"
    assert ingest("order_b_sequence_3.json").status == "accepted"

    replay = ingest("order_b_sequence_1.json")
    assert replay.status == "duplicate"
    assert replay.source_sequence == first.source_sequence

    assert query_scalar("select count(*) from monitoring_evidence") == 3
    assert (
        query_scalar(
            "select last_accepted_sequence from monitoring_sequence_state "
            "where source_instance = :i",
            i=fixture_doc("order_b_sequence_1.json")["source_instance"],
        )
        == 3
    )


# --------------------------------------------------------------------------- #
# Duplicates — concurrent. The reason this file exists.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("concurrency", [2, 5, 10, 20])
def test_concurrent_identical_delivery_yields_exactly_one_evidence_row(
    pg: None, concurrency: int
) -> None:
    """N workers submit the same content-addressed message simultaneously.

    SQLite cannot show what happens here: it serialises writers, so the second
    delivery always finds the first already committed. On PostgreSQL the
    writers genuinely race on the primary key.
    """
    from app.monitoring import receiver

    raw = fixture_bytes("valid_snapshot.json")
    start = threading.Barrier(concurrency)
    results: list[tuple[str | None, BaseException | None]] = []
    lock = threading.Lock()

    def submit() -> None:
        start.wait(timeout=30)
        try:
            ack = receiver.ingest_message(raw, principal())
            outcome: tuple[str | None, BaseException | None] = (ack.status, None)
        except BaseException as exc:
            outcome = (None, exc)
        with lock:
            results.append(outcome)

    with futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        for future in [pool.submit(submit) for _ in range(concurrency)]:
            future.result(timeout=60)

    errors = [exc for _, exc in results if exc is not None]
    assert not errors, f"unhandled errors at concurrency {concurrency}: {errors[:3]}"

    accepted = [status for status, _ in results if status == "accepted"]
    duplicates = [status for status, _ in results if status == "duplicate"]

    assert len(accepted) == 1, f"expected exactly one acceptance, got {len(accepted)}"
    assert len(duplicates) == concurrency - 1
    assert query_scalar("select count(*) from monitoring_evidence") == 1
    assert query_scalar("select count(*) from monitoring_projections") == 1


def test_concurrent_delivery_of_the_same_sequence_accepts_only_one(pg: None) -> None:
    """Two different bodies claiming the same sequence, delivered together.

    Ordered acceptance says sequence N may be accepted once. Two workers that
    both read ``last_accepted = N-1`` under READ COMMITTED would both decide
    "accept" — and SQLite's serialised writers hide that entirely.
    """
    from app.monitoring import receiver

    # Two genuinely different messages for the same (instance, sequence): the
    # producer's own conflict fixture pair.
    first = fixture_bytes("order_a_sequence_1.json")
    second = fixture_bytes("order_a_old_sequence_changed_body.json")
    first_doc = json.loads(first)
    second_doc = json.loads(second)
    assert first_doc["source_instance"] == second_doc["source_instance"]
    assert first_doc["source_sequence"] == second_doc["source_sequence"]
    assert first_doc["message_id"] != second_doc["message_id"]

    start = threading.Barrier(2)
    results: list[tuple[str, str | None, BaseException | None]] = []
    lock = threading.Lock()

    def submit(label: str, raw: bytes) -> None:
        start.wait(timeout=30)
        try:
            ack = receiver.ingest_message(raw, principal())
            outcome: tuple[str, str | None, BaseException | None] = (label, ack.status, None)
        except receiver.ReceiverRefusal as exc:
            outcome = (label, f"refused:{exc.reason}", None)
        except BaseException as exc:
            outcome = (label, None, exc)
        with lock:
            results.append(outcome)

    with futures.ThreadPoolExecutor(max_workers=2) as pool:
        tasks = [pool.submit(submit, "first", first), pool.submit(submit, "second", second)]
        for task in tasks:
            task.result(timeout=60)

    errors = [exc for _, _, exc in results if exc is not None]
    assert not errors, f"unhandled errors: {errors}"

    accepted = [label for label, status, _ in results if status == "accepted"]
    assert len(accepted) == 1, f"two writers both accepted sequence 1: {results}"

    assert query_scalar("select count(*) from monitoring_evidence") == 1
    state = query_all(
        "select last_accepted_sequence, accepted_count from monitoring_sequence_state"
    )
    assert len(state) == 1
    assert state[0][0] == 1
    assert state[0][1] == 1


def test_concurrent_first_messages_of_one_instance_do_not_raise(pg: None) -> None:
    """The sequence-state row is created under contention.

    ``monitoring_sequence_state`` has a unique constraint on
    ``(source_id, source_instance)``. Two workers creating it at once must not
    surface a raw IntegrityError to the producer.
    """
    from app.monitoring import receiver

    raw = fixture_bytes("order_b_sequence_1.json")
    concurrency = 8
    start = threading.Barrier(concurrency)
    errors: list[BaseException] = []
    lock = threading.Lock()

    def submit() -> None:
        start.wait(timeout=30)
        try:
            receiver.ingest_message(raw, principal())
        except receiver.ReceiverRefusal:
            pass
        except BaseException as exc:
            with lock:
                errors.append(exc)

    with futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        for future in [pool.submit(submit) for _ in range(concurrency)]:
            future.result(timeout=60)

    assert not errors, f"unhandled errors creating sequence state: {errors[:3]}"
    assert query_scalar("select count(*) from monitoring_sequence_state") == 1
    assert query_scalar("select count(*) from monitoring_evidence") == 1


# --------------------------------------------------------------------------- #
# Sequence semantics
# --------------------------------------------------------------------------- #
def test_gap_is_refused_and_recovery_is_accepted_in_order(pg: None) -> None:
    """1,2,3 then 5 (refused) then 4 then 5 — the contract's recovery path."""
    from app.monitoring import receiver

    instance = fixture_doc("order_b_sequence_1.json")["source_instance"]

    for name in ("order_b_sequence_1.json", "order_b_sequence_2.json", "order_b_sequence_3.json"):
        assert ingest(name).status == "accepted"

    with pytest.raises(receiver.SequenceRefused) as refusal:
        ingest("order_b_sequence_5.json")
    assert refusal.value.status_code == 409

    # Last accepted stays at 3; the refused message left no trace as data.
    assert (
        query_scalar(
            "select last_accepted_sequence from monitoring_sequence_state "
            "where source_instance = :i",
            i=instance,
        )
        == 3
    )
    assert query_scalar("select count(*) from monitoring_evidence") == 3

    assert ingest("order_b_sequence_4.json").status == "accepted"
    assert ingest("order_b_sequence_5.json").status == "accepted"

    assert (
        query_scalar(
            "select last_accepted_sequence from monitoring_sequence_state "
            "where source_instance = :i",
            i=instance,
        )
        == 5
    )
    assert query_scalar("select count(*) from monitoring_evidence") == 5


def test_a_refused_sequence_never_becomes_evidence_or_a_projection(pg: None) -> None:
    """Sequence refusal is an acceptance decision, not quarantine."""
    from app.monitoring import receiver

    assert ingest("order_b_sequence_1.json").status == "accepted"
    evidence_before = query_scalar("select count(*) from monitoring_evidence")
    projections_before = query_scalar("select count(*) from monitoring_projections")

    refused_id = fixture_doc("sequence_gap_6.json")["message_id"]
    with pytest.raises(receiver.SequenceRefused):
        ingest("sequence_gap_6.json")

    assert query_scalar("select count(*) from monitoring_evidence") == evidence_before
    assert query_scalar("select count(*) from monitoring_projections") == projections_before
    assert (
        query_scalar("select count(*) from monitoring_evidence where message_id = :m", m=refused_id)
        == 0
    )
    # And it is not quarantined either: the message is well formed, merely early.
    assert (
        query_scalar(
            "select count(*) from monitoring_quarantine where declared_message_id = :m",
            m=refused_id,
        )
        == 0
    )


def test_a_new_source_instance_starts_its_own_sequence(pg: None) -> None:
    assert ingest("order_b_sequence_1.json").status == "accepted"
    assert ingest("new_source_instance_sequence_1.json").status == "accepted"

    rows = query_all(
        "select source_instance, last_accepted_sequence from monitoring_sequence_state "
        "order by source_instance"
    )
    assert len(rows) == 2
    assert {sequence for _, sequence in rows} == {1}


# --------------------------------------------------------------------------- #
# Quarantine
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("name", "reason"),
    [
        ("bad_schema_version.json", "schema_version_unsupported"),
        ("invalid_message_id.json", "identity_mismatch"),
        ("malformed_duplicate_keys.json", "malformed"),
        ("excessive_nesting.json", "structural_limit"),
        ("oversized_string.json", "structural_limit"),
    ],
)
def test_defective_messages_are_quarantined_not_projected(pg: None, name: str, reason: str) -> None:
    from app.monitoring import receiver

    with pytest.raises(receiver.ReceiverRefusal) as refusal:
        ingest(name)
    assert refusal.value.reason == reason

    assert query_scalar("select count(*) from monitoring_evidence") == 0
    assert query_scalar("select count(*) from monitoring_projections") == 0
    assert query_scalar("select count(*) from monitoring_quarantine") == 1

    # The original bytes are kept for forensics, bounded.
    assert query_scalar("select count(*) from monitoring_raw_requests") == 1
    stored, length, digest = query_all(
        "select body, byte_length, body_sha256 from monitoring_raw_requests"
    )[0]
    original = fixture_bytes(name)

    # Length and digest always describe the whole body, never the stored prefix.
    assert length == len(original)
    assert digest == hashlib.sha256(original).hexdigest()

    # Every producer fixture is within the preservation cap, so all of them are
    # kept whole — including the one deliberately just over the contract limit.
    from app.monitoring.receiver import MAX_PRESERVED_REQUEST_BYTES

    assert len(original) <= MAX_PRESERVED_REQUEST_BYTES
    assert bytes(stored) == original


def test_a_grossly_oversized_body_is_preserved_only_up_to_the_cap(pg: None) -> None:
    """Refusing a message must not cost more storage than accepting one.

    Staging measurement of the unbounded version: 27 refused requests wrote
    233 MB, and a single gzipped request wrote a 200 MB row. The record stays
    useful — the digest identifies the exact bytes — without being a way to fill
    the database with rejected traffic.
    """
    from app.monitoring import receiver
    from app.monitoring.receiver import MAX_PRESERVED_REQUEST_BYTES

    huge = b'{"schema_version":"monitoring.v1","filler":"' + (b"A" * (8 * 1024 * 1024)) + b'"}'
    with pytest.raises(receiver.StructuralLimitExceeded):
        ingest("", body=huge)

    stored, length, digest = query_all(
        "select body, byte_length, body_sha256 from monitoring_raw_requests"
    )[0]
    assert length == len(huge)
    assert digest == hashlib.sha256(huge).hexdigest()
    assert len(bytes(stored)) == MAX_PRESERVED_REQUEST_BYTES
    assert bytes(stored) == huge[:MAX_PRESERVED_REQUEST_BYTES]


def test_quarantine_survives_its_own_transaction(pg: None) -> None:
    """A refusal must still be investigable after the request fails.

    On PostgreSQL a statement error aborts the transaction, so a refusal path
    that touched the database before failing could lose its own quarantine row.
    """
    from app.monitoring import receiver

    with pytest.raises(receiver.ReceiverRefusal):
        ingest("bad_schema_version.json")

    rows = query_all(
        "select reason, declared_message_id, schema_version from monitoring_quarantine"
    )
    assert len(rows) == 1
    assert rows[0][0] == "schema_version_unsupported"


# --------------------------------------------------------------------------- #
# Projections
# --------------------------------------------------------------------------- #
def test_projection_preserves_every_knowledge_state(pg: None) -> None:
    """UNKNOWN, STALE, INCOMPLETE, UNTRUSTED and SYNTHETIC_CLOCK survive intact."""
    document = fixture_doc("unknown_stale_incomplete_synthetic_salvaged.json")
    assert ingest("unknown_stale_incomplete_synthetic_salvaged.json").status == "accepted"

    row = query_all(
        "select freshness_json, coverage_json, trust_json, runtime_json, source_as_of_json, "
        "source_environment from monitoring_projections"
    )
    assert len(row) == 1
    freshness, coverage, trust, runtime, source_as_of, environment = row[0]

    assert json.loads(freshness) == document["freshness"]
    assert json.loads(freshness)["source"] == "STALE"
    assert json.loads(coverage) == document["coverage"]
    assert json.loads(coverage)["status"] == "INCOMPLETE"
    assert json.loads(trust) == document["trust"]
    assert json.loads(trust)["status"] == "UNTRUSTED"
    assert json.loads(source_as_of)["source_time"]["status"] == "SYNTHETIC_CLOCK"
    # Explicit null stays null, rather than becoming 0 or "".
    assert json.loads(source_as_of)["source_time"]["value"] is None
    # runtime stays an array.
    assert json.loads(runtime) == document["runtime"]
    assert isinstance(json.loads(runtime), list)
    # Producer market reality, not our tier.
    assert environment == document["environment"]


def test_each_message_type_gets_its_own_projection(pg: None) -> None:
    """The projection key separates message types; it does not merge them.

    ``order_b`` sequences 1-3 are a snapshot, an events message and an
    incidents message. They are different subjects, not successive states of
    one, and collapsing them would lose two of the three.
    """
    for name in ("order_b_sequence_1.json", "order_b_sequence_2.json", "order_b_sequence_3.json"):
        assert ingest(name).status == "accepted"

    rows = dict(query_all("select message_type, message_id from monitoring_projections"))
    assert set(rows) == {"monitoring.snapshot", "monitoring.events", "monitoring.incidents"}
    for name, message_type in (
        ("order_b_sequence_1.json", "monitoring.snapshot"),
        ("order_b_sequence_2.json", "monitoring.events"),
        ("order_b_sequence_3.json", "monitoring.incidents"),
    ):
        assert rows[message_type] == fixture_doc(name)["message_id"]


def test_a_later_message_of_the_same_type_supersedes_the_earlier(pg: None) -> None:
    """Sequences 1 and 5 are both snapshots of the same capture on one instance."""
    for name in (
        "order_b_sequence_1.json",
        "order_b_sequence_2.json",
        "order_b_sequence_3.json",
        "order_b_sequence_4.json",
        "order_b_sequence_5.json",
    ):
        assert ingest(name).status == "accepted"

    latest = fixture_doc("order_b_sequence_5.json")
    first = fixture_doc("order_b_sequence_1.json")
    assert latest["message_type"] == first["message_type"]

    snapshot = query_all(
        "select message_id, source_sequence from monitoring_projections where message_type = :t",
        t=latest["message_type"],
    )
    assert len(snapshot) == 1
    assert snapshot[0][0] == latest["message_id"]
    assert snapshot[0][1] == latest["source_sequence"] == "5"

    # A redelivery of the superseded message must not drag the projection back.
    assert ingest("order_b_sequence_1.json").status == "duplicate"
    snapshot = query_all(
        "select message_id from monitoring_projections where message_type = :t",
        t=latest["message_type"],
    )
    assert snapshot[0][0] == latest["message_id"]

    # Superseding never removes the evidence it moved on from.
    assert (
        query_scalar(
            "select count(*) from monitoring_evidence where message_id = :m",
            m=first["message_id"],
        )
        == 1
    )


# --------------------------------------------------------------------------- #
# Rebuild
# --------------------------------------------------------------------------- #
def test_projection_rebuild_is_deterministic_and_leaves_evidence_untouched(pg: None) -> None:
    """Rebuild twice; both must equal the incrementally maintained state."""
    from app.monitoring import projections

    for name in (
        "valid_snapshot.json",
        "valid_events.json",
        "valid_incidents.json",
        "valid_forensic_reference.json",
        "order_b_sequence_1.json",
        "order_b_sequence_2.json",
        "order_b_sequence_3.json",
        "unknown_stale_incomplete_synthetic_salvaged.json",
    ):
        ingest(name)

    def snapshot_projections() -> list[tuple]:
        return query_all(
            "select receiver_deployment_environment, source_id, message_type, capture_ref, "
            "message_id, source_instance, source_sequence, sequence_ordinal, "
            "source_environment, generated_at, received_at, source_as_of_json, "
            "coverage_json, freshness_json, trust_json, runtime_json, payload_json "
            "from monitoring_projections "
            "order by message_type, capture_ref"
        )

    def snapshot_evidence() -> list[tuple]:
        return query_all(
            "select message_id, md5(message_json), request_sha256 from monitoring_evidence "
            "order by message_id"
        )

    original = snapshot_projections()
    evidence_before = snapshot_evidence()
    assert original

    session = session_for()
    try:
        projections.rebuild(session)
        session.commit()
    finally:
        session.close()
    first_rebuild = snapshot_projections()

    session = session_for()
    try:
        projections.rebuild(session)
        session.commit()
    finally:
        session.close()
    second_rebuild = snapshot_projections()

    assert first_rebuild == original
    assert second_rebuild == first_rebuild
    # Evidence is not touched by a rebuild — hash for hash.
    assert snapshot_evidence() == evidence_before


# --------------------------------------------------------------------------- #
# Storage failure
# --------------------------------------------------------------------------- #
def test_health_reports_an_unreachable_database_rather_than_zeros(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A count that could not be read must be UNKNOWN, never 0.

    "No quarantined messages" and "could not ask" are different answers, and a
    health endpoint that conflates them is exactly the kind of fabricated
    reassurance this system exists to avoid. Before this, the endpoint answered
    a database outage with a bare 500 — safe, but silent about why.
    """
    from app.api.routers.monitoring import health
    from app.core.config import get_settings
    from fastapi import Response
    from sqlalchemy.orm import sessionmaker

    # The handler is called directly with a session bound to a closed port. The
    # application cannot be *started* against an unreachable database — it
    # connects during startup and fails closed, which is correct but means a
    # whole-app test could never reach this code path.
    unreachable = PG_URL.replace(":55432/", ":55431/")
    assert unreachable != PG_URL, "expected the staging URL to name port 55432"

    monkeypatch.setenv("OPS_DATABASE_URL", PG_URL)
    monkeypatch.setenv("MONITORING_DEPLOYMENT_ENVIRONMENT", DEPLOYMENT)
    monkeypatch.setenv("MONITORING_SCHEMA_DIR", str(REPO / "schemas" / "monitoring-v1"))
    get_settings.cache_clear()

    dead_engine = create_engine(unreachable, future=True, connect_args={"connect_timeout": 3})
    dead_session = sessionmaker(bind=dead_engine, future=True)()
    response = Response()
    try:
        body = health(response, session=dead_session)
        assert response.status_code == 503
    finally:
        dead_session.close()
        dead_engine.dispose()
        get_settings.cache_clear()

    # Two separate facts, never derived from one another.
    assert body["storageConfigured"] is True
    assert body["databaseReachable"] is False
    # The count is unknown, and says so.
    assert body["quarantinedMessages"] == "UNKNOWN"
    assert body["quarantinedMessages"] != 0
    # And it still refuses to render a verdict on LLS.
    assert body["llsHealth"] == "NOT_DETERMINED_HERE"


def test_an_unreachable_database_is_a_retryable_refusal_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A database that cannot be reached must never look like anything else.

    Staging measurement of the unbounded configuration: every request blocked
    for over two minutes until the *client* gave up, holding a worker the whole
    time, and surfaced either an ambiguous transport timeout or an unhandled
    500. The producer's queue is the only remaining copy of the message, so the
    difference between "retry this" and "something broke" decides whether it
    keeps it.

    Pointed at a closed port rather than stopping the real database, so the
    test is deterministic and needs no process control.
    """
    from app.core.config import get_settings
    from app.database import session as session_module
    from app.monitoring import receiver

    # A port nothing is listening on, in the same database that is otherwise
    # configured — so this exercises "unreachable", not "unconfigured".
    unreachable = PG_URL.replace(":55432/", ":55431/")
    assert unreachable != PG_URL, "expected the staging URL to name port 55432"

    monkeypatch.setenv("OPS_DATABASE_URL", unreachable)
    monkeypatch.setenv("DATABASE_CONNECT_TIMEOUT_SECONDS", "3")
    get_settings.cache_clear()
    session_module._engine = None
    session_module._SessionLocal = None

    try:
        started = time.monotonic()
        with pytest.raises(receiver.StorageUnavailable):
            receiver.ingest_message(fixture_bytes("valid_snapshot.json"), principal())
        elapsed = time.monotonic() - started
        # Bounded, not merely eventual.
        assert elapsed < 30, f"took {elapsed:.1f}s to refuse an unreachable database"
    finally:
        get_settings.cache_clear()
        session_module._engine = None
        session_module._SessionLocal = None


# --------------------------------------------------------------------------- #
# Conservation
# --------------------------------------------------------------------------- #
def test_counts_reconcile_across_a_mixed_run(pg: None) -> None:
    """Accepted, duplicate, refused and quarantined material stays in its lane."""
    from app.monitoring import receiver

    accepted = duplicates = refused = quarantined = 0

    for name in ("order_b_sequence_1.json", "order_b_sequence_2.json"):
        assert ingest(name).status == "accepted"
        accepted += 1

    assert ingest("order_b_sequence_1.json").status == "duplicate"
    duplicates += 1

    with pytest.raises(receiver.SequenceRefused):
        ingest("order_b_sequence_5.json")
    refused += 1

    for name in ("bad_schema_version.json", "invalid_message_id.json"):
        with pytest.raises(receiver.ReceiverRefusal):
            ingest(name)
        quarantined += 1

    # Accepted messages, and only those, are evidence.
    assert query_scalar("select count(*) from monitoring_evidence") == accepted
    # Refused and quarantined material produced no evidence at all.
    assert query_scalar("select count(*) from monitoring_quarantine") == quarantined
    # One projection per message type accepted: a snapshot and an events message.
    assert query_scalar("select count(*) from monitoring_projections") == 2
    assert query_scalar("select count(distinct message_type) from monitoring_projections") == 2

    state = query_all(
        "select accepted_count, duplicate_count, refused_gap_count from monitoring_sequence_state"
    )
    assert len(state) == 1
    assert state[0][0] == accepted
    assert state[0][1] == duplicates
    assert state[0][2] == refused
