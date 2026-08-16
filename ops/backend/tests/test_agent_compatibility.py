"""Backward compatibility with the shipped Google agent.

Phase 2 must not require Google and AWS to be upgraded together. The agent
running today (``raj_monitor`` v4.0.0, protocol 1) sends envelopes with exactly
these fields — ``id, kind, ts, strategy, machine, protocol, data`` and an
optional ``account`` (see ``raj_monitor/types.py::Envelope.as_dict``) — and knows
nothing about ``sequence_id``, ``schema_version`` or ``session_id``.

Adding a credential is the one change Google must make. Everything else is
additive, and these tests pin that.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.schemas.agent import AgentBatch, Envelope
from tests.conftest import agent_headers

# Byte-for-byte the shape `raj_monitor/types.py::Envelope.as_dict()` produces.
SHIPPED_ENVELOPE = {
    "id": "env-a3f9c1d8e0b2",
    "kind": "event",
    "ts": "2026-08-09T09:15:00.123456+00:00",
    "strategy": "S5-10",
    "machine": "gcp-trading-01",
    "protocol": 1,
    "data": {"category": "strategy", "severity": "info", "message": "legacy agent"},
}

# The agent's real batch payload (`transport.py::upload_batch`).
SHIPPED_BATCH = {
    "agentId": "agent-d97def033878",
    "machine": "gcp-trading-01",
    "count": 1,
    "items": [SHIPPED_ENVELOPE],
}


def test_shipped_envelope_parses_without_new_fields() -> None:
    envelope = Envelope(**SHIPPED_ENVELOPE)
    assert envelope.sequence_id is None
    assert envelope.schema_version is None
    assert envelope.session_id is None
    assert envelope.protocol == 1
    assert envelope.kind == "event"


def test_shipped_batch_parses() -> None:
    batch = AgentBatch(**SHIPPED_BATCH)
    assert batch.queueDepth is None
    assert len(batch.items) == 1


def test_envelope_without_account_is_accepted() -> None:
    """`as_dict()` omits `account` entirely when it is None."""
    assert "account" not in SHIPPED_ENVELOPE
    assert Envelope(**SHIPPED_ENVELOPE).account is None


def test_shipped_batch_is_accepted_over_http(client: TestClient) -> None:
    response = client.post("/api/agent/batch", json=SHIPPED_BATCH, headers=agent_headers())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["failed"] == 0
    assert body["rejected"] == 0
    # No sequence numbers from this agent — reported as unknown, not as a gap.
    assert body["lastSequenceId"] is None


def test_upgraded_envelope_is_also_accepted(client: TestClient) -> None:
    upgraded = {
        **SHIPPED_ENVELOPE,
        "id": "env-upgraded-1",
        "sequence_id": 4242,
        "schema_version": 2,
        "session_id": "2026-08-09-NSE",
    }
    response = client.post(
        "/api/agent/batch",
        json={"agentId": "a1", "machine": "gcp-trading-01", "items": [upgraded],
              "queueDepth": 7},
        headers=agent_headers(),
    )
    assert response.status_code == 200, response.text


def test_mixed_old_and_new_envelopes_in_one_batch(client: TestClient) -> None:
    """A rolling agent upgrade produces batches containing both shapes."""
    response = client.post(
        "/api/agent/batch",
        json={
            "agentId": "a1", "machine": "gcp-trading-01",
            "items": [
                {**SHIPPED_ENVELOPE, "id": "mix-old-1"},
                {**SHIPPED_ENVELOPE, "id": "mix-new-1", "sequence_id": 9,
                 "schema_version": 1, "session_id": "2026-08-09-NSE"},
            ],
        },
        headers=agent_headers(),
    )
    assert response.status_code == 200, response.text
    assert response.json()["rejected"] == 0


def test_all_shipped_envelope_kinds_are_routable(client: TestClient) -> None:
    """Every kind in `raj_monitor/constants.py::ALL_KINDS` must be accepted.

    A kind the server does not know is dead-lettered, so a mismatch here would
    silently discard a whole category of real telemetry.
    """
    shipped_kinds = [
        "start", "stop", "heartbeat", "metric", "metrics",
        "trade", "position", "event", "error", "log",
    ]
    items = [
        {"id": f"kind-{kind}", "kind": kind, "machine": "gcp-trading-01",
         "strategy": "S5-10", "protocol": 1,
         "data": {"message": "x", "name": "m", "value": 1.0, "symbol": "NIFTY",
                  "direction": "long", "action": "close", "quantity": 1}}
        for kind in shipped_kinds
    ]
    response = client.post(
        "/api/agent/batch",
        json={"agentId": "a1", "machine": "gcp-trading-01", "items": items},
        headers=agent_headers(),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rejected"] == 0, f"unroutable shipped kinds: {body.get('outcomes')}"


def test_heartbeat_from_unregistered_machine_creates_it(client: TestClient) -> None:
    """Regression: this envelope used to be silently dropped.

    ``_dispatch_inner`` passes an explicit ``agentId: None`` when the payload has
    no agent id, and ``dict.get("agentId", default)`` does not apply its default
    to a present-but-None key — so building the implicit ``AgentRegister`` raised
    a ValidationError. The old ``except Exception: continue`` in ``handle_batch``
    swallowed it and still acknowledged the batch, so a host whose register call
    had not landed (backend down at agent boot — precisely the retry path) never
    appeared on the dashboard, and the heartbeat was gone from the agent's queue.
    """
    response = client.post(
        "/api/agent/batch",
        json={
            "agentId": "agent-fresh-01", "machine": "never-registered-host",
            "items": [{
                "id": "hb-fresh-1", "kind": "heartbeat",
                "machine": "never-registered-host", "strategy": "agent", "protocol": 1,
                "data": {"cpu": 12.5, "ram": 40.0, "health": "healthy"},
            }],
        },
        headers=agent_headers(),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["rejected"] == 0, body.get("outcomes")
    assert body["processed"] == 1

    machines = client.get("/api/machines").json()
    assert any(m["name"] == "never-registered-host" for m in machines), (
        "a heartbeat must be able to create its own machine record"
    )


def test_ack_keeps_the_original_five_keys(client: TestClient) -> None:
    """The frontend and the agent both read the original ack shape."""
    response = client.post(
        "/api/agent/batch", json=SHIPPED_BATCH, headers=agent_headers()
    )
    body = response.json()
    for key in ("accepted", "received", "kind", "processed", "machineId"):
        assert key in body, f"ack lost the original key {key!r}"


def test_gzip_batch_upload_still_works(client: TestClient) -> None:
    """The agent gzips payloads above 512 bytes (`COMPRESS_MIN_BYTES`)."""
    import gzip
    import json as _json

    items = [
        {**SHIPPED_ENVELOPE, "id": f"gz-{i}",
         "data": {"category": "strategy", "severity": "info", "message": "padding" * 20}}
        for i in range(10)
    ]
    raw = _json.dumps({"agentId": "a1", "machine": "gcp-trading-01", "items": items})
    assert len(raw) > 512, "payload should be large enough that the agent would gzip it"

    response = client.post(
        "/api/agent/batch",
        content=gzip.compress(raw.encode()),
        headers={**agent_headers(), "Content-Encoding": "gzip",
                 "Content-Type": "application/json"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["rejected"] == 0
