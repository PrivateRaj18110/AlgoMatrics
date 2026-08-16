"""Phase 3 offline/recovery dashboard coverage."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from app.models import utcnow
from app.services.agent_service import machine_id_for
from fastapi.testclient import TestClient

from tests.conftest import agent_headers


def _machine(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


def _row(summary: dict, machine_id: str) -> dict:
    return next(row for row in summary["machines"] if row["machineId"] == machine_id)


def test_recovery_summary_derives_offline_duration_from_stale_heartbeat(
    client: TestClient,
) -> None:
    machine = _machine("recovery-offline")
    machine_id = machine_id_for(machine)
    old = (utcnow() - timedelta(seconds=360)).isoformat()

    response = client.post(
        "/api/agent/heartbeat",
        json={
            "agentId": "agent-recovery",
            "machine": machine,
            "ts": old,
            "health": "healthy",
            "queueDepth": 8,
            "oldestPendingAgeSec": 120,
            "transportState": "queued",
            "currentSessionId": "2026-08-10-NSE",
        },
        headers=agent_headers(),
    )
    assert response.status_code == 200, response.text

    summary = client.get("/api/recovery/summary")
    assert summary.status_code == 200, summary.text
    body = summary.json()
    row = _row(body, machine_id)
    assert row["status"] == "offline"
    assert row["recoveryState"] == "offline"
    assert row["heartbeatAgeSec"] >= 300
    assert row["offlineDurationSec"] >= 180
    assert row["queueDepth"] == 8
    assert row["oldestPendingAgeSec"] == 120
    assert row["currentSessionId"] == "2026-08-10-NSE"
    assert "heartbeat is beyond offline threshold" in row["warnings"]


def test_recovery_envelope_updates_recovery_state_and_backlog(client: TestClient) -> None:
    machine = _machine("recovery-live")
    machine_id = machine_id_for(machine)

    heartbeat = client.post(
        "/api/agent/heartbeat",
        json={
            "agentId": "agent-recovery",
            "machine": machine,
            "health": "healthy",
            "queueDepth": 0,
            "transportState": "connected",
        },
        headers=agent_headers(),
    )
    assert heartbeat.status_code == 200, heartbeat.text

    recovery = client.post(
        "/api/agent/batch",
        json={
            "agentId": "agent-recovery",
            "machine": machine,
            "items": [
                {
                    "id": f"recovery-{uuid4().hex}",
                    "kind": "recovery",
                    "machine": machine,
                    "strategy": "ops-agent",
                    "data": {
                        "state": "recovering",
                        "eventsRecovered": 42,
                        "eodBacklog": 2,
                        "queueDepth": 3,
                    },
                }
            ],
        },
        headers=agent_headers(),
    )
    assert recovery.status_code == 200, recovery.text

    summary = client.get("/api/recovery/summary")
    assert summary.status_code == 200, summary.text
    row = _row(summary.json(), machine_id)
    assert row["status"] == "online"
    assert row["recoveryState"] == "recovering"
    assert row["transportState"] == "recovering"
    assert row["eventsRecovered"] == 42
    assert row["eodBacklog"] == 2
    assert row["lastRecovery"]
    assert "EOD datasets are not finalized" in row["warnings"]
