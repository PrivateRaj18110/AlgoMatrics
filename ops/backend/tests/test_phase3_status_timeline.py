"""Phase 3 heartbeat/status and event timeline coverage."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from app.models import utcnow
from app.repositories.sql import derive_machine_status
from app.services.agent_service import machine_id_for
from tests.conftest import agent_headers


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def test_machine_status_derives_from_configurable_heartbeat_age() -> None:
    now = utcnow()
    assert derive_machine_status(
        "online",
        "online",
        None,
        live=True,
        now=now,
        degraded_after_seconds=30,
        offline_after_seconds=120,
    ) == ("unknown", "unknown")
    assert derive_machine_status(
        "online",
        "online",
        now - timedelta(seconds=5),
        live=True,
        now=now,
        degraded_after_seconds=30,
        offline_after_seconds=120,
    ) == ("online", "online")
    assert derive_machine_status(
        "online",
        "online",
        now - timedelta(seconds=45),
        live=True,
        now=now,
        degraded_after_seconds=30,
        offline_after_seconds=120,
    ) == ("degraded", "degraded")
    assert derive_machine_status(
        "online",
        "online",
        now - timedelta(seconds=180),
        live=True,
        now=now,
        degraded_after_seconds=30,
        offline_after_seconds=120,
    ) == ("offline", "offline")
    assert derive_machine_status(
        "online",
        "online",
        None,
        live=False,
        now=now,
        degraded_after_seconds=30,
        offline_after_seconds=120,
    ) == ("online", "online")


def test_heartbeat_updates_phase3_machine_current_state(client: TestClient) -> None:
    machine = f"phase3-host-{uuid4().hex[:8]}"
    mid = machine_id_for(machine)

    register = client.post(
        "/api/agent/register",
        json={
            "agentId": "agent-phase3",
            "machine": machine,
            "sdkVersion": "4.1.0",
            "hostname": "gcp-phase3",
            "environment": "paper",
        },
        headers=agent_headers(),
    )
    assert register.status_code == 200, register.text

    heartbeat = client.post(
        "/api/agent/heartbeat",
        json={
            "agentId": "agent-phase3",
            "machine": machine,
            "health": "healthy",
            "cpu": 11.5,
            "ram": 33.0,
            "disk": 44.0,
            "queueDepth": 7,
            "oldestPendingAgeSec": 12,
            "transportState": "connected",
            "currentSessionId": "2026-08-10-NSE",
            "tradingProcessState": "running",
            "lastEodStatus": "complete",
        },
        headers=agent_headers(),
    )
    assert heartbeat.status_code == 200, heartbeat.text

    machine_response = client.get(f"/api/machines/{mid}")
    assert machine_response.status_code == 200, machine_response.text
    body = machine_response.json()
    assert body["agentId"] == "agent-phase3"
    assert body["agentVersion"] == "4.1.0"
    assert body["hostname"] == "gcp-phase3"
    assert body["environment"] == "paper"
    assert body["queueDepth"] == 7
    assert body["oldestPendingAgeSec"] == 12
    assert body["transportState"] == "connected"
    assert body["currentSessionId"] == "2026-08-10-NSE"
    assert body["tradingProcessState"] == "running"
    assert body["lastEodStatus"] == "complete"


def test_phase3_event_vocabulary_is_accepted_and_timeline_is_filterable(client: TestClient) -> None:
    machine = f"phase3-events-{uuid4().hex[:8]}"
    session_id = f"session-{uuid4().hex}"
    symbol = f"P3{uuid4().hex[:6].upper()}"
    kinds = [
        "system_status",
        "strategy_status",
        "signal",
        "order",
        "fill",
        "pnl",
        "risk",
        "sync_status",
        "recovery",
    ]
    items = [
        {
            "id": _uid(kind),
            "kind": kind,
            "machine": machine,
            "strategy": "phase3-smoke",
            "session_id": session_id,
            "sequence_id": index + 1,
            "data": {
                "status": "complete" if kind == "sync_status" else "ok",
                "symbol": symbol,
                "severity": "warning" if kind == "risk" else "info",
                "quantity": 1,
                "price": 100.5,
                "secretToken": "must-not-leak",
            },
        }
        for index, kind in enumerate(kinds)
    ]

    response = client.post(
        "/api/agent/batch",
        json={
            "agentId": "agent-phase3-events",
            "machine": machine,
            "items": items,
            "queueDepth": 0,
        },
        headers=agent_headers(),
    )
    assert response.status_code == 200, response.text
    ack = response.json()
    assert ack["processed"] == len(kinds)
    assert ack["rejected"] == 0

    order_events = client.get(
        f"/api/events?eventType=order&symbol={symbol}&sessionId={session_id}"
    )
    assert order_events.status_code == 200, order_events.text
    rows = order_events.json()
    assert rows, "the order telemetry should be queryable from the timeline"
    assert rows[0]["eventType"] == "order"
    assert rows[0]["symbol"] == symbol
    assert rows[0]["sessionId"] == session_id
    assert rows[0]["sequenceId"] == 4
    assert "must-not-leak" not in (rows[0].get("payloadSummary") or "")

    risk_events = client.get(f"/api/events?severity=warning&category=risk&symbol={symbol}")
    assert risk_events.status_code == 200, risk_events.text
    assert any(row["eventType"] == "risk" for row in risk_events.json())
