"""Read-only trading-session API coverage."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import DASHBOARD_TOKEN, SCOPED_MACHINE, SCOPED_TOKEN, agent_headers


def _dashboard_headers() -> dict[str, str]:
    return {"X-Raj-Dashboard-Token": DASHBOARD_TOKEN}


def test_session_list_and_detail_are_read_only_dashboard_views(client: TestClient) -> None:
    session_id = "prelive-session-2026-08-14"
    ingest = client.post(
        "/api/agent/batch",
        json={
            "agentId": "agent-session-test",
            "machine": SCOPED_MACHINE,
            "queueDepth": 0,
            "items": [
                {
                    "id": "session-api-env-1",
                    "kind": "event",
                    "machine": SCOPED_MACHINE,
                    "strategy": "observer",
                    "session_id": session_id,
                    "sequence_id": 1,
                    "schema_version": 3,
                    "data": {
                        "category": "strategy",
                        "severity": "info",
                        "type": "session_probe",
                        "message": "session api probe",
                    },
                },
                {
                    "id": "session-api-env-2",
                    "kind": "trade",
                    "machine": SCOPED_MACHINE,
                    "strategy": "observer",
                    "session_id": session_id,
                    "sequence_id": 2,
                    "schema_version": 3,
                    "data": {
                        "symbol": "NIFTY",
                        "direction": "long",
                        "action": "close",
                        "entry": 100,
                        "exit": 101,
                        "quantity": 1,
                        "pnl": 1,
                    },
                },
            ],
        },
        headers=agent_headers(SCOPED_TOKEN, "agent-session-test"),
    )
    assert ingest.status_code == 200, ingest.text

    sessions = client.get("/api/sessions", headers=_dashboard_headers())
    assert sessions.status_code == 200, sessions.text
    row = next(item for item in sessions.json() if item["sessionId"] == session_id)
    assert row["status"] == "open"
    assert row["eventCount"] == 2
    assert row["tradeCount"] == 1

    detail = client.get(f"/api/sessions/{session_id}", headers=_dashboard_headers())
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["session"]["sessionId"] == session_id
    assert body["recentEvents"][0]["sessionId"] == session_id
    assert body["recentEvents"][0]["payloadSummary"]
    assert body["eodDatasets"] == []

    missing = client.get("/api/sessions/missing-session", headers=_dashboard_headers())
    assert missing.status_code == 404
