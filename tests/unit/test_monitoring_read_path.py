"""The platform's read path over the monitoring.v1 projections.

The receiver in ``ops/backend`` owns these tables; the platform only reads them.
What is worth testing here is that the read layer does not undo any of the
guarantees the receiver established on the way in — the producer's objects
survive verbatim, the two environment axes stay separate, and no freshness is
computed from arrival time.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from algo_platform.modules.operations.infrastructure.monitoring_store import MonitoringStore

# The subset of the receiver's schema this read path touches. Kept here rather
# than imported from ops/backend on purpose: the platform must not depend on the
# receiver's Python, only on the shape of the tables it publishes.
SCHEMA = """
CREATE TABLE monitoring_projections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receiver_deployment_environment TEXT NOT NULL DEFAULT 'UNKNOWN',
    organisation_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    message_type TEXT NOT NULL,
    capture_ref TEXT NOT NULL DEFAULT '',
    message_id TEXT NOT NULL,
    source_instance TEXT NOT NULL,
    source_sequence TEXT NOT NULL,
    sequence_ordinal BIGINT NOT NULL,
    source_environment TEXT NOT NULL,
    generated_at TIMESTAMP NOT NULL,
    received_at TIMESTAMP NOT NULL,
    source_as_of_json TEXT NOT NULL,
    coverage_json TEXT NOT NULL,
    freshness_json TEXT NOT NULL,
    trust_json TEXT NOT NULL,
    runtime_json TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE monitoring_sequence_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organisation_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_instance TEXT NOT NULL,
    last_accepted_sequence BIGINT NOT NULL,
    last_accepted_message_id TEXT NOT NULL,
    accepted_count BIGINT NOT NULL DEFAULT 0,
    duplicate_count BIGINT NOT NULL DEFAULT 0,
    refused_gap_count BIGINT NOT NULL DEFAULT 0,
    refused_old_count BIGINT NOT NULL DEFAULT 0,
    observed_gaps TEXT NOT NULL DEFAULT '[]',
    first_seen_at TIMESTAMP NOT NULL,
    last_seen_at TIMESTAMP NOT NULL
);

CREATE TABLE monitoring_evidence (
    message_id TEXT PRIMARY KEY,
    organisation_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    source_instance TEXT NOT NULL,
    source_sequence TEXT NOT NULL,
    sequence_ordinal BIGINT NOT NULL,
    message_type TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    source_environment TEXT NOT NULL,
    receiver_deployment_environment TEXT NOT NULL DEFAULT 'UNKNOWN',
    generated_at TIMESTAMP NOT NULL,
    received_at TIMESTAMP NOT NULL,
    source_as_of_json TEXT NOT NULL,
    coverage_json TEXT NOT NULL,
    freshness_json TEXT NOT NULL,
    trust_json TEXT NOT NULL,
    runtime_json TEXT NOT NULL,
    freshness_source TEXT,
    trust_status TEXT,
    coverage_status TEXT,
    capture_ref TEXT,
    request_sha256 TEXT NOT NULL,
    message_json TEXT NOT NULL
);
"""

NOW = datetime(2026, 9, 11, 9, 1, 34, tzinfo=UTC)

ORG_A = "00000000-0000-0000-0000-000000000001"
ORG_B = "00000000-0000-0000-0000-000000000002"

# Mirrors the producer's own qualified-value shape: the value key is present and
# explicitly null, which a receiver must not strip and must not read as zero.
PAYLOAD = {
    "capture_ref": "historical-final",
    "execution": {
        "independent_broker_state": {
            "reason": "not_available",
            "status": "UNKNOWN",
            "value": None,
        }
    },
}
FRESHNESS = {
    "derived_at": "2026-09-11T09:01:34.627414+00:00",
    "reason": "fixture_preserves_stale_without_live_upgrade",
    "source": "STALE",
}
TRUST = {"independent_broker": "UNKNOWN", "scope": "fixture", "status": "UNTRUSTED"}
COVERAGE = {"capture_status": "salvaged", "reason": "partial", "status": "INCOMPLETE"}
SOURCE_AS_OF = {
    "acquired_at_ns": "1789117280359665700",
    "source_time": {
        "reason": "no_common_qualified_source_clock",
        "status": "UNKNOWN",
        "value": None,
    },
    "valid_at": "per_object_source_cut",
}
RUNTIME = ["historical-final/2503001"]


@pytest.fixture
def store(tmp_path: Path) -> Iterator[MonitoringStore]:
    path = tmp_path / "monitoring.db"
    url = f"sqlite:///{path.as_posix()}"
    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        for statement in SCHEMA.strip().split(";"):
            if statement.strip():
                conn.execute(text(statement))
        _seed(conn)
    engine.dispose()

    instance = MonitoringStore(url)
    yield instance
    instance.close()
    with suppress(OSError):
        path.unlink()


def _seed(conn) -> None:
    insert = text(
        """
        INSERT INTO monitoring_projections (
            receiver_deployment_environment, organisation_id, source_id, message_type, capture_ref,
            message_id, source_instance, source_sequence, sequence_ordinal,
            source_environment, generated_at, received_at, source_as_of_json,
            coverage_json, freshness_json, trust_json, runtime_json, payload_json,
            updated_at
        ) VALUES (
            :deployment, :organisation_id, :source_id, :message_type, :capture_ref,
            :message_id, :source_instance, :source_sequence, :sequence_ordinal,
            :source_environment, :generated_at, :received_at, :source_as_of,
            :coverage, :freshness, :trust, :runtime, :payload, :updated_at
        )
        """
    )

    def row(deployment: str, message_type: str, message_id: str, organisation_id: str = ORG_A) -> dict:
        return {
            "deployment": deployment,
            "organisation_id": organisation_id,
            "source_id": "lls-monitoring-prod",
            "message_type": message_type,
            "capture_ref": "historical-final",
            "message_id": message_id,
            "source_instance": "main-01" if organisation_id == ORG_A else "main-02",
            "source_sequence": "1",
            "sequence_ordinal": 1,
            # Market reality — deliberately not a deployment tier.
            "source_environment": "offline_fixture",
            "generated_at": NOW,
            "received_at": NOW,
            "source_as_of": json.dumps(SOURCE_AS_OF),
            "coverage": json.dumps(COVERAGE),
            "freshness": json.dumps(FRESHNESS),
            "trust": json.dumps(TRUST),
            "runtime": json.dumps(RUNTIME),
            "payload": json.dumps(PAYLOAD),
            "updated_at": NOW,
        }

    conn.execute(insert, row("staging", "monitoring.snapshot", "mon1/a", ORG_A))
    conn.execute(insert, row("staging", "monitoring.events", "mon1/b", ORG_A))
    conn.execute(insert, row("production", "monitoring.snapshot", "mon1/c", ORG_A))
    conn.execute(insert, row("staging", "monitoring.snapshot", "mon1/org-b", ORG_B))

    conn.execute(
        text(
            """
            INSERT INTO monitoring_sequence_state (
                organisation_id, source_id, source_instance, last_accepted_sequence,
                last_accepted_message_id, accepted_count, duplicate_count,
                refused_gap_count, refused_old_count, observed_gaps,
                first_seen_at, last_seen_at
            ) VALUES (
                :org_a, 'lls-monitoring-prod', 'main-01', 4, 'mon1/d', 4, 2, 1, 1,
                '[{"expected": 2, "received": 3, "action": "refuse_gap", "at": "x"}]',
                :now, :now
            ), (
                :org_b, 'lls-monitoring-prod', 'main-02', 10, 'mon1/org-b-seq', 10, 0, 0, 0,
                '[]',
                :now, :now
            )
            """
        ),
        {"org_a": ORG_A, "org_b": ORG_B, "now": NOW},
    )

    conn.execute(
        text(
            """
            INSERT INTO monitoring_evidence (
                message_id, organisation_id, source_id, source_instance, source_sequence,
                sequence_ordinal, message_type, schema_version, source_environment,
                receiver_deployment_environment, generated_at, received_at, source_as_of_json,
                coverage_json, freshness_json, trust_json, runtime_json, freshness_source,
                trust_status, coverage_status, capture_ref, request_sha256, message_json
            ) VALUES (
                'mon1/ev-a', :org_a, 'lls-monitoring-prod', 'main-01', '1',
                1, 'monitoring.snapshot', 'monitoring.v1', 'offline_fixture',
                'staging', :now, :now, :as_of,
                :coverage, :freshness, :trust, :runtime, 'STALE',
                'UNTRUSTED', 'INCOMPLETE', 'historical-final', 'sha256abc', '{}'
            ), (
                'mon1/ev-b', :org_b, 'lls-monitoring-prod', 'main-02', '1',
                1, 'monitoring.snapshot', 'monitoring.v1', 'offline_fixture',
                'staging', :now, :now, :as_of,
                :coverage, :freshness, :trust, :runtime, 'STALE',
                'UNTRUSTED', 'INCOMPLETE', 'historical-final', 'sha256xyz', '{}'
            )
            """
        ),
        {
            "org_a": ORG_A,
            "org_b": ORG_B,
            "now": NOW,
            "as_of": json.dumps(SOURCE_AS_OF),
            "coverage": json.dumps(COVERAGE),
            "freshness": json.dumps(FRESHNESS),
            "trust": json.dumps(TRUST),
            "runtime": json.dumps(RUNTIME),
        },
    )


# --------------------------------------------------------------------------- #
def test_unconfigured_store_returns_empty_not_fixtures() -> None:
    """An empty monitoring dashboard is honest. Invented monitoring data is not."""
    unconfigured = MonitoringStore(None)
    assert unconfigured.configured is False
    assert unconfigured.current_state(organisation_id=ORG_A) == []
    assert unconfigured.sources(organisation_id=ORG_A) == []
    assert unconfigured.history(organisation_id=ORG_A) == []


def test_missing_organisation_fails_closed_returns_empty(store: MonitoringStore) -> None:
    """Without an explicit organisation context, read queries must fail closed."""
    assert store.current_state(deployment="staging", organisation_id=None) == []
    assert store.sources(organisation_id=None) == []
    assert store.history(deployment="staging", organisation_id=None) == []


def test_producer_objects_survive_the_read_path(store: MonitoringStore) -> None:
    """The read layer must not undo what the receiver preserved."""
    row = next(
        item
        for item in store.current_state(deployment="staging", organisation_id=ORG_A)
        if item["message_type"] == "monitoring.snapshot"
    )
    assert row["freshness"] == FRESHNESS
    assert row["trust"] == TRUST
    assert row["coverage"] == COVERAGE
    assert row["source_as_of"] == SOURCE_AS_OF
    assert row["payload"] == PAYLOAD


def test_explicit_nulls_are_preserved(store: MonitoringStore) -> None:
    """`{"value": null, "status": "UNKNOWN"}` keeps its null."""
    row = store.current_state(deployment="staging", organisation_id=ORG_A)[0]
    broker = row["payload"]["execution"]["independent_broker_state"]
    assert broker["status"] == "UNKNOWN"
    assert "value" in broker
    assert broker["value"] is None


def test_runtime_stays_an_array(store: MonitoringStore) -> None:
    """Never collapsed into LIVE / HISTORICAL / SIMULATED."""
    row = store.current_state(deployment="staging", organisation_id=ORG_A)[0]
    assert row["runtime"] == RUNTIME
    assert isinstance(row["runtime"], list)


def test_stale_is_not_upgraded_and_no_horizon_is_computed(store: MonitoringStore) -> None:
    """The producer asserted STALE; the read path carries it, unmodified."""
    row = store.current_state(deployment="staging", organisation_id=ORG_A)[0]
    assert row["freshness"]["source"] == "STALE"
    # No horizon exists in monitoring.v1 and none is invented here.
    assert "stale_after" not in json.dumps(row)


def test_untrusted_is_not_upgraded(store: MonitoringStore) -> None:
    row = store.current_state(deployment="staging", organisation_id=ORG_A)[0]
    assert row["trust"]["status"] == "UNTRUSTED"


def test_the_two_environment_axes_stay_separate(store: MonitoringStore) -> None:
    row = store.current_state(deployment="staging", organisation_id=ORG_A)[0]
    assert row["source_environment"] == "offline_fixture"  # market reality
    assert row["receiver_deployment_environment"] == "staging"  # our tier
    assert row["source_environment"] != row["receiver_deployment_environment"]


def test_deployment_isolation_is_enforced_by_the_query(store: MonitoringStore) -> None:
    """A staging row is never loaded into a production response at all."""
    staging = store.current_state(deployment="staging", organisation_id=ORG_A)
    production = store.current_state(deployment="production", organisation_id=ORG_A)

    assert {row["message_id"] for row in staging} == {"mon1/a", "mon1/b"}
    assert {row["message_id"] for row in production} == {"mon1/c"}
    assert all(row["receiver_deployment_environment"] == "staging" for row in staging)


def test_message_type_filter_narrows_without_crossing_deployments(
    store: MonitoringStore,
) -> None:
    assert store.current_state(deployment="staging", organisation_id=ORG_A, message_type="monitoring.events")
    assert store.current_state(deployment="production", organisation_id=ORG_A, message_type="monitoring.events") == []


def test_sequence_is_reported_as_a_string(store: MonitoringStore) -> None:
    """The wire representation is a string; the read path does not re-render it."""
    row = store.current_state(deployment="staging", organisation_id=ORG_A)[0]
    assert row["source_sequence"] == "1"
    assert isinstance(row["source_sequence"], str)


def test_refusals_are_reported_as_observability(store: MonitoringStore) -> None:
    rows = store.sources(organisation_id=ORG_A)
    assert len(rows) == 1
    assert rows[0]["last_accepted_sequence"] == "4"
    assert rows[0]["refused_gap_count"] == 1
    assert rows[0]["refused_old_count"] == 1
    assert rows[0]["observed_refusals"][0]["expected"] == 2


def test_organisation_tenancy_isolation(store: MonitoringStore) -> None:
    """Projections, sequence state, and evidence history must be strictly partitioned by organisation."""
    # Current state isolation
    org_a_items = store.current_state(deployment="staging", organisation_id=ORG_A)
    org_b_items = store.current_state(deployment="staging", organisation_id=ORG_B)
    assert {row["message_id"] for row in org_a_items} == {"mon1/a", "mon1/b"}
    assert {row["message_id"] for row in org_b_items} == {"mon1/org-b"}

    # Sources isolation
    org_a_sources = store.sources(organisation_id=ORG_A)
    org_b_sources = store.sources(organisation_id=ORG_B)
    assert len(org_a_sources) == 1
    assert org_a_sources[0]["source_instance"] == "main-01"
    assert len(org_b_sources) == 1
    assert org_b_sources[0]["source_instance"] == "main-02"

    # History isolation
    org_a_history = store.history(deployment="staging", organisation_id=ORG_A)
    org_b_history = store.history(deployment="staging", organisation_id=ORG_B)
    assert [row["message_id"] for row in org_a_history] == ["mon1/ev-a"]
    assert [row["message_id"] for row in org_b_history] == ["mon1/ev-b"]

    # Unknown organisation isolation
    unknown_org = "00000000-0000-0000-0000-000000000099"
    assert store.current_state(deployment="staging", organisation_id=unknown_org) == []
    assert store.sources(organisation_id=unknown_org) == []
    assert store.history(deployment="staging", organisation_id=unknown_org) == []


def test_corrupt_json_degrades_to_empty_rather_than_raising(tmp_path: Path) -> None:
    """A malformed stored row must not take the whole monitoring page down."""
    path = tmp_path / "corrupt.db"
    url = f"sqlite:///{path.as_posix()}"
    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        for statement in SCHEMA.strip().split(";"):
            if statement.strip():
                conn.execute(text(statement))
        conn.execute(
            text(
                """
                INSERT INTO monitoring_projections (
                    receiver_deployment_environment, organisation_id, source_id, message_type, capture_ref,
                    message_id, source_instance, source_sequence, sequence_ordinal,
                    source_environment, generated_at, received_at, source_as_of_json,
                    coverage_json, freshness_json, trust_json, runtime_json, payload_json,
                    updated_at
                ) VALUES (
                    'staging', :org_a, 's', 'monitoring.snapshot', '', 'mon1/x', 'i', '1', 1,
                    'offline_fixture', :now, :now, 'not json', 'not json', 'not json',
                    'not json', 'not json', 'not json', :now
                )
                """
            ),
            {"org_a": ORG_A, "now": NOW},
        )
    engine.dispose()

    store = MonitoringStore(url)
    try:
        row = store.current_state(deployment="staging", organisation_id=ORG_A)[0]
        assert row["payload"] == {}
        assert row["freshness"] == {}
        assert row["runtime"] == []
    finally:
        store.close()
