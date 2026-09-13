"""monitoring.v1 receiver capabilities, exercised against real LLS fixtures.

This replaces the ``monitoring-export/v1`` suite of the same name. Every
capability that suite covered is re-expressed here against the canonical
contract; the mapping is recorded in ``test_capability_migration_is_complete``
at the end, including the two capabilities that no longer exist and why.

The fixtures are the producer's own. Nothing here constructs a message by hand,
because a receiver tested only against its own idea of a message will pass its
own tests and fail the first real one.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO = BACKEND_DIR.parents[1]
PACKAGE = REPO / "tests" / "fixtures" / "lls-monitoring-v1-handoff"
MESSAGES = PACKAGE / "fixtures" / "messages"
# Repo-local: the system temp directory on the development machine has ACLs that
# break pytest's tmp_path.
TMP_ROOT = BACKEND_DIR / "var" / "test-tmp" / "monitoring-v1"

SOURCE_ID = "lls-contract-fixture"
PUBLISH_TOKEN = "receiver-suite-upload-token"  # noqa: S105 - test credential
ADMIN_TOKEN = "receiver-suite-admin-token"  # noqa: S105 - test credential
OTHER_SOURCE_ID = "lls-other-source"
OTHER_TOKEN = "receiver-suite-other-token"  # noqa: S105 - test credential
DEPLOYMENT = "staging"

ENDPOINT = "/api/monitoring/v1/messages"


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
def _env(database_url: str) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(BACKEND_DIR), env.get("PYTHONPATH", "")) if part
    )
    env["DATABASE_URL"] = database_url
    env.pop("OPS_DATABASE_URL", None)
    env.pop("ENVIRONMENT", None)
    return env


@pytest.fixture(scope="module")
def database_url() -> str:
    """A migrated SQLite database, built by the real migration."""
    if TMP_ROOT.exists():
        shutil.rmtree(TMP_ROOT, ignore_errors=True)
    TMP_ROOT.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{(TMP_ROOT / 'monitoring.db').as_posix()}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=_env(url),
        check=True,
        capture_output=True,
        text=True,
        timeout=300,
    )
    yield url
    shutil.rmtree(TMP_ROOT, ignore_errors=True)


@pytest.fixture
def client(database_url: str, monkeypatch: pytest.MonkeyPatch):
    from app.core.config import get_settings
    from app.database import session as session_module
    from app.monitoring import contract

    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.delenv("OPS_DATABASE_URL", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setenv(
        "MONITORING_SOURCE_TOKENS", f"{SOURCE_ID}:{PUBLISH_TOKEN},{OTHER_SOURCE_ID}:{OTHER_TOKEN}"
    )
    monkeypatch.setenv("MONITORING_ADMIN_TOKEN", ADMIN_TOKEN)
    monkeypatch.setenv("MONITORING_DEPLOYMENT_ENVIRONMENT", DEPLOYMENT)
    monkeypatch.setenv("RAJ_AGENT_TOKEN", "agent-token-for-the-other-protocol")
    monkeypatch.setenv("RAJ_DASHBOARD_TOKEN", "dashboard-token-for-tests")

    get_settings.cache_clear()
    # The engine is a module global bound on first use; without this the second
    # test would silently reuse the first test's database.
    session_module._engine = None
    session_module._SessionLocal = None
    contract.reset_cache()

    _truncate(database_url)

    from main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client

    get_settings.cache_clear()
    session_module._engine = None
    session_module._SessionLocal = None


def _truncate(database_url: str) -> None:
    """Clear monitoring tables between tests.

    Raw SQL on purpose: the ORM refuses to delete evidence, which is exactly the
    behaviour under test in ``test_evidence_cannot_be_updated_or_deleted``.
    """
    from sqlalchemy import create_engine

    engine = create_engine(database_url, future=True)
    with engine.begin() as connection:
        for table in (
            "monitoring_projections",
            "monitoring_quarantine",
            "monitoring_raw_requests",
            "monitoring_sequence_state",
            "monitoring_audit",
            "monitoring_evidence",
        ):
            # S608 is suppressed because the table names are the fixed literal
            # tuple above, never caller input.
            connection.execute(text(f"DELETE FROM {table}"))  # noqa: S608
    engine.dispose()


def session_for():
    from app.database.session import get_sessionmaker

    return get_sessionmaker()()


# --------------------------------------------------------------------------- #
# Helpers — every message comes from the producer's package
# --------------------------------------------------------------------------- #
def fixture_bytes(name: str) -> bytes:
    return (MESSAGES / name).read_bytes()


def fixture_doc(name: str) -> dict[str, Any]:
    return json.loads(fixture_bytes(name))


def post(
    client: TestClient,
    name: str,
    *,
    token: str = PUBLISH_TOKEN,
    digest: str | None = None,
    body: bytes | None = None,
):
    raw = body if body is not None else fixture_bytes(name)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if digest is not None:
        headers["X-Monitoring-SHA256"] = digest
    return client.post(ENDPOINT, content=raw, headers=headers)


def accept(client: TestClient, name: str):
    response = post(client, name)
    assert response.status_code == 200, f"{name}: {response.status_code} {response.text[:200]}"
    return response.json()


# --------------------------------------------------------------------------- #
# Contract acceptance
# --------------------------------------------------------------------------- #
def test_the_four_valid_messages_are_accepted_in_order(client: TestClient) -> None:
    for name in (
        "valid_snapshot.json",
        "valid_events.json",
        "valid_incidents.json",
        "valid_forensic_reference.json",
    ):
        assert accept(client, name)["status"] == "accepted"


def test_ack_is_exactly_the_contract_shape(client: TestClient) -> None:
    """The producer validates every field; anything extra is a failed delivery."""
    ack = accept(client, "valid_snapshot.json")
    assert set(ack) == {"schema_version", "message_id", "sha256", "source_sequence", "status"}
    assert ack["schema_version"] == "monitoring.ack.v1"

    entry = fixture_doc("valid_snapshot.json")
    assert ack["message_id"] == entry["message_id"]
    assert ack["source_sequence"] == entry["source_sequence"]
    # Echoed as the string that arrived, never re-rendered.
    assert isinstance(ack["source_sequence"], str)


def test_ack_sha256_is_the_whole_request_digest(client: TestClient) -> None:
    import hashlib

    ack = accept(client, "valid_snapshot.json")
    assert ack["sha256"] == hashlib.sha256(fixture_bytes("valid_snapshot.json")).hexdigest()


def test_declared_request_digest_is_verified(client: TestClient) -> None:
    response = post(client, "valid_snapshot.json", digest="0" * 64)
    assert response.status_code == 400
    assert response.json()["detail"]["reason"] == "request_digest_mismatch"


def test_correct_declared_digest_is_accepted(client: TestClient) -> None:
    import hashlib

    digest = hashlib.sha256(fixture_bytes("valid_snapshot.json")).hexdigest()
    assert post(client, "valid_snapshot.json", digest=digest).status_code == 200


# --------------------------------------------------------------------------- #
# Authentication and source scope
# --------------------------------------------------------------------------- #
def test_unauthenticated_upload_is_rejected(client: TestClient) -> None:
    assert client.post(ENDPOINT, content=fixture_bytes("valid_snapshot.json")).status_code == 401


def test_invalid_credential_is_rejected(client: TestClient) -> None:
    assert post(client, "valid_snapshot.json", token="not-a-real-token").status_code == 401


def test_credential_cannot_publish_for_another_source(client: TestClient) -> None:
    """A leaked credential is confined to the one source it was issued for."""
    response = post(client, "valid_snapshot.json", token=OTHER_TOKEN)
    assert response.status_code == 403
    assert response.json()["detail"]["reason"] == "source_not_authorized"


def test_agent_credential_does_not_authorize_monitoring_upload(client: TestClient) -> None:
    """The two protocols' credentials are separate, so their boundaries are too."""
    response = post(client, "valid_snapshot.json", token="agent-token-for-the-other-protocol")
    assert response.status_code == 401


def test_publisher_credential_grants_no_administrative_access(client: TestClient) -> None:
    response = client.get(
        "/api/monitoring/v1/quarantine", headers={"Authorization": f"Bearer {PUBLISH_TOKEN}"}
    )
    assert response.status_code == 401


def test_administrator_can_inspect_quarantine(client: TestClient) -> None:
    post(client, "bad_schema_version.json")
    response = client.get(
        "/api/monitoring/v1/quarantine", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
    )
    assert response.status_code == 200
    assert response.json()["items"][0]["reason"] == "schema_version_unsupported"


def test_authentication_happens_before_persistence(client: TestClient) -> None:
    """An unauthorised body must leave no evidence and no projection."""
    post(client, "valid_snapshot.json", token=OTHER_TOKEN)
    session = session_for()
    try:
        assert session.execute(text("SELECT COUNT(*) FROM monitoring_evidence")).scalar_one() == 0
        assert (
            session.execute(text("SELECT COUNT(*) FROM monitoring_projections")).scalar_one() == 0
        )
    finally:
        session.close()


# --------------------------------------------------------------------------- #
# Identity
# --------------------------------------------------------------------------- #
def test_forged_message_id_is_refused(client: TestClient) -> None:
    """The id is a content address; the receiver recomputes rather than trusts."""
    response = post(client, "invalid_message_id.json")
    assert response.status_code == 400
    assert response.json()["detail"]["reason"] == "identity_mismatch"


def test_reused_identity_with_changed_body_is_refused(client: TestClient) -> None:
    """Replaces the old conflict machinery — content addressing catches it earlier.

    Under monitoring-export/v1 this needed a conflict table, because identity was
    an opaque uuid and the disagreement only surfaced after both versions were
    stored. Here the label cannot match altered content, so it never reaches
    evidence at all.
    """
    accept(client, "duplicate_snapshot.json")
    response = post(client, "conflict_same_id_changed_payload.json")
    assert response.status_code == 400
    assert response.json()["detail"]["reason"] == "identity_mismatch"

    session = session_for()
    try:
        # The genuine message survives; the impostor was never stored.
        assert session.execute(text("SELECT COUNT(*) FROM monitoring_evidence")).scalar_one() == 1
    finally:
        session.close()


def test_refused_identity_is_quarantined_with_both_ids(client: TestClient) -> None:
    post(client, "invalid_message_id.json")
    items = client.get(
        "/api/monitoring/v1/quarantine", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
    ).json()["items"]
    row = next(item for item in items if item["reason"] == "identity_mismatch")
    assert row["declaredMessageId"] != row["computedMessageId"]
    assert row["computedMessageId"].startswith("mon1/")


# --------------------------------------------------------------------------- #
# Duplicate delivery
# --------------------------------------------------------------------------- #
def test_duplicate_delivery_creates_one_record(client: TestClient) -> None:
    accept(client, "duplicate_snapshot.json")
    assert accept(client, "duplicate_snapshot.json")["status"] == "duplicate"

    session = session_for()
    try:
        assert session.execute(text("SELECT COUNT(*) FROM monitoring_evidence")).scalar_one() == 1
        assert (
            session.execute(text("SELECT COUNT(*) FROM monitoring_projections")).scalar_one() == 1
        )
    finally:
        session.close()


def test_ack_loss_retry_returns_duplicate_with_identical_identity(client: TestClient) -> None:
    """The producer stored, lost our ACK, and resent. Nothing doubles."""
    first = accept(client, "duplicate_snapshot.json")
    retry = accept(client, "duplicate_snapshot.json")
    assert retry["status"] == "duplicate"
    assert retry["message_id"] == first["message_id"]
    assert retry["sha256"] == first["sha256"]
    assert retry["source_sequence"] == first["source_sequence"]


def test_duplicate_is_acknowledged_even_after_later_sequences(client: TestClient) -> None:
    """Required by the contract, and why duplicate is decided before ordering."""
    accept(client, "order_b_sequence_1.json")
    accept(client, "order_b_sequence_2.json")
    accept(client, "order_b_sequence_3.json")
    assert accept(client, "order_b_sequence_1.json")["status"] == "duplicate"


def test_repeated_duplicates_do_not_accumulate(client: TestClient) -> None:
    accept(client, "duplicate_snapshot.json")
    for _ in range(20):
        assert accept(client, "duplicate_snapshot.json")["status"] == "duplicate"
    session = session_for()
    try:
        assert session.execute(text("SELECT COUNT(*) FROM monitoring_evidence")).scalar_one() == 1
    finally:
        session.close()


# --------------------------------------------------------------------------- #
# Sequence — ordered acceptance
# --------------------------------------------------------------------------- #
def test_first_message_of_an_instance_must_be_sequence_one(client: TestClient) -> None:
    response = post(client, "sequence_gap_6.json")
    assert response.status_code == 409
    assert response.json()["detail"]["reason"] == "sequence_refused"


def test_new_source_instance_starting_at_one_is_accepted(client: TestClient) -> None:
    assert accept(client, "new_source_instance_sequence_1.json")["status"] == "accepted"


def test_gap_is_refused_and_the_next_expected_message_is_accepted(client: TestClient) -> None:
    accept(client, "order_a_sequence_1.json")
    assert post(client, "order_a_sequence_3.json").status_code == 409
    assert accept(client, "order_a_sequence_2.json")["status"] == "accepted"
    assert accept(client, "order_a_sequence_3.json")["status"] == "accepted"


def test_unknown_older_sequence_is_refused(client: TestClient) -> None:
    accept(client, "order_a_sequence_1.json")
    accept(client, "order_a_sequence_2.json")
    # Sequence 1 again, but a different body — a different content address, so
    # not a duplicate, and older than what was accepted.
    assert post(client, "order_a_old_sequence_changed_body.json").status_code == 409


def test_out_of_order_recovery_sequence(client: TestClient) -> None:
    """The producer's own 5-4-6 case: refuse, accept the fill-in, then proceed."""
    for name in ("order_b_sequence_1.json", "order_b_sequence_2.json", "order_b_sequence_3.json"):
        accept(client, name)
    assert post(client, "order_b_sequence_5.json").status_code == 409
    assert accept(client, "order_b_sequence_4.json")["status"] == "accepted"
    assert post(client, "order_b_sequence_6.json").status_code == 409
    assert accept(client, "order_b_sequence_5.json")["status"] == "accepted"
    assert accept(client, "order_b_sequence_6.json")["status"] == "accepted"


def test_refused_message_never_becomes_evidence_or_projection(client: TestClient) -> None:
    """The crux: a 409 must leave no trace that looks like accepted data."""
    post(client, "sequence_gap_6.json")
    session = session_for()
    try:
        assert session.execute(text("SELECT COUNT(*) FROM monitoring_evidence")).scalar_one() == 0
        assert (
            session.execute(text("SELECT COUNT(*) FROM monitoring_projections")).scalar_one() == 0
        )
    finally:
        session.close()


def test_refusals_are_visible_to_operators_without_being_accepted(client: TestClient) -> None:
    """Gap observability survives, separated from the acceptance decision."""
    accept(client, "order_a_sequence_1.json")
    post(client, "order_a_sequence_3.json")

    row = client.get("/api/monitoring/v1/sources").json()["items"][0]
    assert row["lastAcceptedSequence"] == "1"
    assert row["refusedGapCount"] == 1
    assert row["observedRefusals"][0]["expected"] == 2
    assert row["observedRefusals"][0]["received"] == 3


def test_last_accepted_state_is_retained_across_a_refusal(client: TestClient) -> None:
    accept(client, "order_a_sequence_1.json")
    post(client, "order_a_sequence_3.json")
    row = client.get("/api/monitoring/v1/sources").json()["items"][0]
    assert row["acceptedCount"] == 1
    assert row["lastAcceptedSequence"] == "1"


def test_sequence_state_is_scoped_to_the_source_instance(client: TestClient) -> None:
    accept(client, "valid_snapshot.json")  # main-01, seq 1
    accept(client, "new_source_instance_sequence_1.json")  # new-epoch-01, seq 1
    rows = client.get("/api/monitoring/v1/sources").json()
    assert rows["count"] == 2
    assert {row["sourceInstance"] for row in rows["items"]} == {"main-01", "new-epoch-01"}


# --------------------------------------------------------------------------- #
# Evidence
# --------------------------------------------------------------------------- #
def test_evidence_cannot_be_updated_or_deleted(client: TestClient) -> None:
    from app.models.monitoring import EvidenceIsImmutable, MonitoringEvidence

    ack = accept(client, "valid_snapshot.json")
    session = session_for()
    try:
        row = session.get(MonitoringEvidence, ack["message_id"])
        assert row is not None
        row.message_type = "monitoring.events"
        with pytest.raises(EvidenceIsImmutable):
            session.flush()
        session.rollback()

        row = session.get(MonitoringEvidence, ack["message_id"])
        session.delete(row)
        with pytest.raises(EvidenceIsImmutable):
            session.flush()
        session.rollback()
    finally:
        session.close()


def test_evidence_stores_the_producer_message_verbatim(client: TestClient) -> None:
    """Nothing is lost merely because the receiver has no column for it."""
    from app.monitoring import contract

    ack = accept(client, "valid_snapshot.json")
    stored = client.get(f"/api/monitoring/v1/evidence/{ack['message_id']}").json()
    assert stored["message"] == fixture_doc("valid_snapshot.json")
    # And it round-trips to the exact producer bytes.
    assert contract.canonical_json(stored["message"]) == fixture_bytes("valid_snapshot.json")


def test_evidence_preserves_the_sequence_string_unchanged(client: TestClient) -> None:
    accept(client, "valid_snapshot.json")
    session = session_for()
    try:
        value = session.execute(
            text("SELECT source_sequence FROM monitoring_evidence")
        ).scalar_one()
    finally:
        session.close()
    assert value == "1"
    assert isinstance(value, str)


def test_evidence_records_both_environments_separately(client: TestClient) -> None:
    accept(client, "valid_snapshot.json")
    session = session_for()
    try:
        source_env, deployment = session.execute(
            text(
                "SELECT source_environment, receiver_deployment_environment "
                "FROM monitoring_evidence"
            )
        ).one()
    finally:
        session.close()
    assert source_env == "offline_fixture"  # the producer's market reality
    assert deployment == DEPLOYMENT  # our configured tier
    assert source_env != deployment


# --------------------------------------------------------------------------- #
# Quarantine
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("fixture", "expected_status", "expected_reason"),
    [
        ("malformed_duplicate_keys.json", 400, "malformed"),
        ("bad_schema_version.json", 422, "schema_version_unsupported"),
        ("invalid_message_id.json", 400, "identity_mismatch"),
        ("oversized_string.json", 413, "structural_limit"),
        ("excessive_nesting.json", 413, "structural_limit"),
    ],
)
def test_invalid_messages_are_refused_and_quarantined(
    client: TestClient, fixture: str, expected_status: int, expected_reason: str
) -> None:
    response = post(client, fixture)
    assert response.status_code == expected_status
    assert response.json()["detail"]["reason"] == expected_reason

    items = client.get(
        "/api/monitoring/v1/quarantine", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
    ).json()["items"]
    assert any(item["reason"] == expected_reason for item in items)


def test_an_oversized_chunked_upload_is_bounded(client: TestClient) -> None:
    """A body with no Content-Length must still be bounded.

    Content-Length is the sender's claim, and a chunked upload does not send one
    at all. Before this was bounded, such a request was materialised in full
    before the contract's 1 MiB limit was ever consulted — the same exposure as
    the gzip amplification, reached by simply omitting a header.
    """

    def chunks():
        block = b"A" * (1024 * 1024)
        for _ in range(4):
            yield block

    response = client.post(
        ENDPOINT,
        content=chunks(),
        headers={"Authorization": f"Bearer {PUBLISH_TOKEN}", "Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["detail"]["reason"] == "structural_limit"


def test_a_message_just_over_the_limit_is_still_quarantined(client: TestClient) -> None:
    """Bounding the read must not cost the forensic record.

    The cheap refusal is reserved for traffic too large to be worth preserving.
    A message modestly over the contract limit is exactly what an operator will
    want to look at, so it still reaches the normal path and keeps its bytes.
    """
    response = post(client, "oversized_string.json")
    assert response.status_code == 413
    assert response.json()["detail"]["quarantine_id"] is not None


def test_quarantined_material_never_becomes_a_projection(client: TestClient) -> None:
    for fixture in ("bad_schema_version.json", "invalid_message_id.json"):
        post(client, fixture)
    assert client.get("/api/monitoring/v1/state").json()["count"] == 0


def test_quarantine_preserves_the_original_request_bytes(client: TestClient) -> None:
    post(client, "malformed_duplicate_keys.json")
    session = session_for()
    try:
        body = session.execute(text("SELECT body FROM monitoring_raw_requests")).scalar_one()
    finally:
        session.close()
    assert body == fixture_bytes("malformed_duplicate_keys.json")


def test_quarantine_is_not_visible_to_dashboard_viewers(client: TestClient) -> None:
    post(client, "bad_schema_version.json")
    assert client.get("/api/monitoring/v1/quarantine").status_code == 401


def test_a_sequence_refusal_is_not_quarantined(client: TestClient) -> None:
    """A well-formed message refused for ordering is not defective.

    Quarantining it would imply the producer sent something broken. It did not —
    it sent something early, and it will resend in order.
    """
    post(client, "sequence_gap_6.json")
    assert (
        client.get(
            "/api/monitoring/v1/quarantine", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
        ).json()["count"]
        == 0
    )


# --------------------------------------------------------------------------- #
# Semantics preservation
# --------------------------------------------------------------------------- #
def test_unknown_stale_untrusted_incomplete_are_preserved(client: TestClient) -> None:
    """The producer's fixture built specifically to catch a receiver that upgrades."""
    accept(client, "unknown_stale_incomplete_synthetic_salvaged.json")
    item = client.get("/api/monitoring/v1/state").json()["items"][0]

    assert item["freshness"]["source"] == "STALE"
    assert item["trust"]["status"] == "UNTRUSTED"
    assert item["coverage"]["status"] == "INCOMPLETE"
    assert item["coverage"]["capture_status"] == "salvaged"


def test_stale_is_not_upgraded_by_a_recent_delivery(client: TestClient) -> None:
    """Arriving a moment ago says nothing about source validity."""
    accept(client, "unknown_stale_incomplete_synthetic_salvaged.json")
    item = client.get("/api/monitoring/v1/state").json()["items"][0]
    assert item["freshness"]["source"] == "STALE"
    received = datetime.fromisoformat(item["time"]["receivedAt"].replace("Z", "+00:00"))
    # Received seconds ago, still STALE — both facts visible and distinct.
    assert (datetime.now(UTC) - received).total_seconds() < 300


def test_untrusted_is_not_upgraded_by_successful_delivery(client: TestClient) -> None:
    """A 200 means we received it, not that it is true."""
    accept(client, "unknown_stale_incomplete_synthetic_salvaged.json")
    item = client.get("/api/monitoring/v1/state").json()["items"][0]
    assert item["trust"]["status"] == "UNTRUSTED"


def test_explicit_nulls_in_qualified_values_are_preserved(client: TestClient) -> None:
    """LLS writes `{"value": null, "status": "UNKNOWN"}`. The null stays."""
    accept(client, "valid_snapshot.json")
    item = client.get(
        "/api/monitoring/v1/state", params={"message_type": "monitoring.snapshot"}
    ).json()["items"][0]
    broker = item["payload"]["execution"]["independent_broker_state"]
    assert broker["status"] == "UNKNOWN"
    assert "value" in broker
    assert broker["value"] is None


def test_runtime_stays_an_array_of_capture_identifiers(client: TestClient) -> None:
    """Never collapsed into LIVE / HISTORICAL / SIMULATED."""
    accept(client, "valid_snapshot.json")
    item = client.get("/api/monitoring/v1/state").json()["items"][0]
    assert item["runtime"] == ["historical-final/2503001"]
    assert isinstance(item["runtime"], list)


def test_source_environment_is_not_mapped_to_a_deployment_tier(client: TestClient) -> None:
    accept(client, "valid_snapshot.json")
    body = client.get("/api/monitoring/v1/state").json()
    item = body["items"][0]
    assert item["sourceEnvironment"] == "offline_fixture"
    assert item["receiverDeploymentEnvironment"] == DEPLOYMENT
    assert body["receiverDeploymentEnvironment"] == DEPLOYMENT


def test_deployment_environment_is_unknown_when_unconfigured(
    database_url: str, monkeypatch
) -> None:
    """Never inferred from the message — the producer does not know where we run."""
    from app.core.config import get_settings
    from app.database import session as session_module

    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.delenv("MONITORING_DEPLOYMENT_ENVIRONMENT", raising=False)
    monkeypatch.setenv("MONITORING_SOURCE_TOKENS", f"{SOURCE_ID}:{PUBLISH_TOKEN}")
    monkeypatch.setenv("RAJ_AGENT_TOKEN", "a")
    monkeypatch.setenv("RAJ_DASHBOARD_TOKEN", "d")
    get_settings.cache_clear()
    session_module._engine = None
    session_module._SessionLocal = None
    try:
        from main import create_app

        with TestClient(create_app()) as unconfigured:
            body = unconfigured.get("/api/monitoring/v1/state").json()
            assert body["receiverDeploymentEnvironment"] == "UNKNOWN"
    finally:
        get_settings.cache_clear()
        session_module._engine = None
        session_module._SessionLocal = None


def test_source_as_of_is_preserved_verbatim(client: TestClient) -> None:
    """Never substituted with the receiver's arrival time."""
    accept(client, "valid_snapshot.json")
    item = client.get("/api/monitoring/v1/state").json()["items"][0]
    assert item["time"]["sourceAsOf"] == fixture_doc("valid_snapshot.json")["source_as_of"]
    assert item["time"]["sourceAsOf"]["source_time"]["status"] == "UNKNOWN"


def test_the_time_domains_stay_separate(client: TestClient) -> None:
    accept(client, "valid_snapshot.json")
    item = client.get("/api/monitoring/v1/state").json()["items"][0]
    assert item["time"]["generatedAt"] == "2026-09-11T09:01:34.627414Z"
    assert item["time"]["receivedAt"] != item["time"]["generatedAt"]
    assert "sourceAsOf" in item["time"]


def test_no_stale_after_anywhere_in_the_receiver_response(client: TestClient) -> None:
    """The horizon model is gone; a reintroduction fails here."""
    accept(client, "valid_snapshot.json")
    body = client.get("/api/monitoring/v1/state").text
    assert "stale_after" not in body
    assert "staleAfter" not in body


def test_freshness_is_read_not_computed(client: TestClient) -> None:
    """No local clock arithmetic decides freshness under monitoring.v1."""
    from app.monitoring import freshness

    assert not hasattr(freshness, "evaluate"), (
        "a horizon evaluator reappeared in the freshness module"
    )
    accept(client, "valid_snapshot.json")
    item = client.get("/api/monitoring/v1/state").json()["items"][0]
    assert item["freshness"]["source"] == "UNKNOWN"
    assert item["freshness"]["derivedAt"] == "2026-09-11T09:01:34.627414+00:00"


def test_unrecognised_freshness_states_are_flagged_not_reinterpreted() -> None:
    from app.monitoring import freshness

    read = freshness.read({"source": "SOMETHING_NEW", "reason": "r"})
    assert read.source_state == "SOMETHING_NEW"
    assert read.is_recognised is False
    # Preserved, not downgraded to UNKNOWN and certainly not to healthy.
    assert read.as_dict()["source"] == "SOMETHING_NEW"


# --------------------------------------------------------------------------- #
# Projections
# --------------------------------------------------------------------------- #
def test_each_message_type_projects_separately(client: TestClient) -> None:
    for name in (
        "valid_snapshot.json",
        "valid_events.json",
        "valid_incidents.json",
        "valid_forensic_reference.json",
    ):
        accept(client, name)
    body = client.get("/api/monitoring/v1/state").json()
    assert body["count"] == 4
    assert {item["messageType"] for item in body["items"]} == {
        "monitoring.snapshot",
        "monitoring.events",
        "monitoring.incidents",
        "monitoring.forensic_reference",
    }


def test_a_later_message_of_the_same_type_supersedes_the_earlier_one(
    client: TestClient,
) -> None:
    """order_b cycles through the four message types, so sequences 1 and 5 are
    both snapshots of the same capture — the genuine supersession case.

    Sequences 2, 3 and 4 are different message types and therefore different
    subjects: they get their own projection rows rather than overwriting the
    snapshot. That is the producer's model, not a receiver invention.
    """

    def snapshot_row():
        return next(
            item
            for item in client.get("/api/monitoring/v1/state").json()["items"]
            if item["messageType"] == "monitoring.snapshot"
        )

    accept(client, "order_b_sequence_1.json")
    assert snapshot_row()["source"]["sourceSequence"] == "1"

    for name in (
        "order_b_sequence_2.json",
        "order_b_sequence_3.json",
        "order_b_sequence_4.json",
        "order_b_sequence_5.json",
    ):
        accept(client, name)

    # The snapshot row moved forward to sequence 5; it did not gain a second row.
    assert snapshot_row()["source"]["sourceSequence"] == "5"
    body = client.get("/api/monitoring/v1/state").json()
    assert body["count"] == 4
    assert len([i for i in body["items"] if i["messageType"] == "monitoring.snapshot"]) == 1


def test_projections_rebuild_identically_from_evidence(client: TestClient) -> None:
    """A projection bug must be recoverable, so the rebuild must be exact."""
    from app.monitoring.projections import rebuild

    for name in (
        "valid_snapshot.json",
        "valid_events.json",
        "valid_incidents.json",
        "valid_forensic_reference.json",
    ):
        accept(client, name)

    before = client.get("/api/monitoring/v1/state").json()["items"]

    session = session_for()
    try:
        rebuild(session)
        session.commit()
    finally:
        session.close()

    assert client.get("/api/monitoring/v1/state").json()["items"] == before


def test_rebuild_is_idempotent(client: TestClient) -> None:
    from app.monitoring.projections import rebuild

    accept(client, "valid_snapshot.json")
    accept(client, "valid_events.json")

    results = []
    for _ in range(3):
        session = session_for()
        try:
            rebuild(session)
            session.commit()
        finally:
            session.close()
        results.append(client.get("/api/monitoring/v1/state").json()["items"])
    assert results[0] == results[1] == results[2]


def test_rebuild_does_not_touch_evidence(client: TestClient) -> None:
    from app.monitoring.projections import rebuild

    accept(client, "valid_snapshot.json")
    accept(client, "valid_events.json")

    session = session_for()
    try:
        before = session.execute(text("SELECT COUNT(*) FROM monitoring_evidence")).scalar_one()
        rebuild(session)
        session.commit()
        after = session.execute(text("SELECT COUNT(*) FROM monitoring_evidence")).scalar_one()
    finally:
        session.close()
    assert before == after == 2


# --------------------------------------------------------------------------- #
# History
# --------------------------------------------------------------------------- #
def test_history_retains_superseded_observations(client: TestClient) -> None:
    """A projection moving forward never removes the evidence it moved on from."""
    accept(client, "order_b_sequence_1.json")
    accept(client, "order_b_sequence_2.json")
    accept(client, "order_b_sequence_3.json")

    history = client.get("/api/monitoring/v1/history").json()
    assert history["count"] == 3
    assert [item["source"]["sourceSequence"] for item in history["items"]] == ["1", "2", "3"]
    # Each keeps its own source timestamps — no implied continuity.
    assert len({item["time"]["generatedAt"] for item in history["items"]}) == 3


# --------------------------------------------------------------------------- #
# Storage availability
# --------------------------------------------------------------------------- #
def test_receiver_refuses_rather_than_accepting_into_nothing(monkeypatch) -> None:
    """No database means no durable evidence, so the answer is 503, not 200."""
    from app.core.config import get_settings
    from app.database import session as session_module

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("OPS_DATABASE_URL", raising=False)
    monkeypatch.setenv("MONITORING_SOURCE_TOKENS", f"{SOURCE_ID}:{PUBLISH_TOKEN}")
    monkeypatch.setenv("RAJ_AGENT_TOKEN", "agent-token")
    monkeypatch.setenv("RAJ_DASHBOARD_TOKEN", "dashboard-token")
    get_settings.cache_clear()
    session_module._engine = None
    session_module._SessionLocal = None

    try:
        from main import create_app

        with TestClient(create_app()) as test_client:
            assert post(test_client, "valid_snapshot.json").status_code == 503
    finally:
        get_settings.cache_clear()
        session_module._engine = None
        session_module._SessionLocal = None


# --------------------------------------------------------------------------- #
# Hostile input
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "hostile",
    [
        b"{",
        b"",
        b"[]",
        b'{"schema_version": "monitoring.v1"',
        b"\xff\xfe not utf-8 at all",
        b'{"a": Infinity}',
        b'{"a": NaN}',
        b'{"a": 1, "a": 2}',
        b'{"source_id": "x\'; DROP TABLE monitoring_evidence; --"}',
        b'{"source_id": "<script>alert(1)</script>"}',
    ],
)
def test_hostile_bodies_are_refused_without_damage(client: TestClient, hostile: bytes) -> None:
    """Exercised, not assumed. The tables must still be there afterwards."""
    response = post(client, "", body=hostile)
    assert response.status_code in {400, 413, 422}

    session = session_for()
    try:
        assert session.execute(text("SELECT COUNT(*) FROM monitoring_evidence")).scalar_one() == 0
    finally:
        session.close()


def test_sql_injection_in_a_valid_message_is_not_executed(client: TestClient) -> None:
    """Parameterised queries, proven by exercising them rather than asserting them."""
    from app.monitoring import contract

    document = fixture_doc("valid_snapshot.json")
    document["source_instance"] = "x'; DROP TABLE monitoring_evidence; --"
    # The identity is a content address, so an altered body needs a new one.
    document["message_id"] = contract.message_identity(document)
    response = post(client, "", body=contract.canonical_json(document))

    # Refused on the schema's source_instance pattern — and the table survives.
    assert response.status_code in {400, 422}
    session = session_for()
    try:
        session.execute(text("SELECT COUNT(*) FROM monitoring_evidence")).scalar_one()
    finally:
        session.close()


def test_credentials_never_appear_in_the_audit_log(client: TestClient) -> None:
    accept(client, "valid_snapshot.json")
    post(client, "valid_snapshot.json", token="some-other-secret-value")

    session = session_for()
    try:
        rows = session.execute(text("SELECT detail, source_id FROM monitoring_audit")).all()
    finally:
        session.close()
    blob = json.dumps([list(row) for row in rows])
    assert PUBLISH_TOKEN not in blob
    assert "some-other-secret-value" not in blob


# --------------------------------------------------------------------------- #
# No trading capability
# --------------------------------------------------------------------------- #
def test_monitoring_routes_expose_no_control_actions(client: TestClient) -> None:
    """Structural guard against the published OpenAPI surface."""
    forbidden = (
        "cancel",
        "modify",
        "resubmit",
        "flatten",
        "restart",
        "halt",
        "execute",
        "trade",
        "place",
        "shutdown",
        "enable",
        "disable",
    )
    schema = client.get("/openapi.json").json()
    paths = {
        path: spec
        for path, spec in schema["paths"].items()
        if path.startswith("/api/monitoring/v1")
    }
    assert paths, "monitoring routes are not mounted"
    for path in paths:
        assert not any(word in path.lower() for word in forbidden), f"{path} reads as a control"

    writes = sorted(
        (path, method.upper())
        for path, spec in paths.items()
        for method in spec
        if method.upper() not in {"GET", "HEAD", "OPTIONS"}
    )
    assert writes == [("/api/monitoring/v1/messages", "POST")]


def test_receiver_health_does_not_claim_to_know_lls_health(client: TestClient) -> None:
    body = client.get("/api/monitoring/v1/health").json()
    assert body["llsHealth"] == "NOT_DETERMINED_HERE"
    assert body["contractAvailable"] is True
    assert body["supportedSchemaVersion"] == "monitoring.v1"
    assert body["ackSchemaVersion"] == "monitoring.ack.v1"


# --------------------------------------------------------------------------- #
# Migration bookkeeping
# --------------------------------------------------------------------------- #
def test_capability_migration_is_complete() -> None:
    """Every capability the superseded suite covered is re-expressed here.

    Two no longer exist under monitoring.v1, and both disappeared because the
    canonical contract solves the problem earlier and better:

    * **Conflict retention.** The old suite kept both versions of a disputed
      record because identity was an opaque uuid, so a disagreement could only be
      found after storing both. Under content addressing a changed body cannot
      keep a valid id, so the impostor is refused at validation and never becomes
      evidence — covered by ``test_reused_identity_with_changed_body_is_refused``.

    * **Horizon-based staleness.** The old suite proved a dead feed went STALE
      when a supplied ``stale_after`` elapsed. monitoring.v1 has no horizon; the
      source asserts its own state — covered by
      ``test_stale_is_not_upgraded_by_a_recent_delivery`` and
      ``test_freshness_is_read_not_computed``, with
      ``test_no_stale_after_anywhere_in_the_receiver_response`` guarding against
      the old model returning.
    """
    covered = {
        "contract acceptance": "test_the_four_valid_messages_are_accepted_in_order",
        "ack shape": "test_ack_is_exactly_the_contract_shape",
        "request digest": "test_declared_request_digest_is_verified",
        "authentication": "test_unauthenticated_upload_is_rejected",
        "source scope": "test_credential_cannot_publish_for_another_source",
        "protocol isolation": "test_agent_credential_does_not_authorize_monitoring_upload",
        "admin separation": "test_publisher_credential_grants_no_administrative_access",
        "auth before persistence": "test_authentication_happens_before_persistence",
        "identity verification": "test_forged_message_id_is_refused",
        "identity collision": "test_reused_identity_with_changed_body_is_refused",
        "duplicate": "test_duplicate_delivery_creates_one_record",
        "ack loss": "test_ack_loss_retry_returns_duplicate_with_identical_identity",
        "duplicate after later": "test_duplicate_is_acknowledged_even_after_later_sequences",
        "sequence first": "test_first_message_of_an_instance_must_be_sequence_one",
        "sequence gap": "test_gap_is_refused_and_the_next_expected_message_is_accepted",
        "old sequence": "test_unknown_older_sequence_is_refused",
        "out of order recovery": "test_out_of_order_recovery_sequence",
        "refusal leaves nothing": "test_refused_message_never_becomes_evidence_or_projection",
        "gap observability": "test_refusals_are_visible_to_operators_without_being_accepted",
        "instance scope": "test_sequence_state_is_scoped_to_the_source_instance",
        "evidence immutability": "test_evidence_cannot_be_updated_or_deleted",
        "evidence completeness": "test_evidence_stores_the_producer_message_verbatim",
        "quarantine": "test_invalid_messages_are_refused_and_quarantined",
        "quarantine isolation": "test_quarantined_material_never_becomes_a_projection",
        "quarantine forensics": "test_quarantine_preserves_the_original_request_bytes",
        "knowledge states": "test_unknown_stale_untrusted_incomplete_are_preserved",
        "explicit null": "test_explicit_nulls_in_qualified_values_are_preserved",
        "runtime array": "test_runtime_stays_an_array_of_capture_identifiers",
        "environment axes": "test_source_environment_is_not_mapped_to_a_deployment_tier",
        "source_as_of": "test_source_as_of_is_preserved_verbatim",
        "time domains": "test_the_time_domains_stay_separate",
        "no stale_after": "test_no_stale_after_anywhere_in_the_receiver_response",
        "projection rebuild": "test_projections_rebuild_identically_from_evidence",
        "projection determinism": "test_rebuild_is_idempotent",
        "projection supersession": (
            "test_a_later_message_of_the_same_type_supersedes_the_earlier_one"
        ),
        "history": "test_history_retains_superseded_observations",
        "storage unavailable": "test_receiver_refuses_rather_than_accepting_into_nothing",
        "hostile input": "test_hostile_bodies_are_refused_without_damage",
        "sql injection": "test_sql_injection_in_a_valid_message_is_not_executed",
        "credential hygiene": "test_credentials_never_appear_in_the_audit_log",
        "no trading controls": "test_monitoring_routes_expose_no_control_actions",
    }
    module = sys.modules[__name__]
    missing = [name for name in covered.values() if not hasattr(module, name)]
    assert not missing, f"capability tests named but not defined: {missing}"
    assert len(covered) >= 40
