"""Tests for system_health telemetry ingestion, storage, and classification."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.repositories import system_health_repo
from app.schemas.agent import AgentBatch, Envelope
from app.services.agent_service import handle_batch
from app.services.telemetry_classification import resolve_dispatch_kind
from tests.conftest import agent_headers


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def _health_envelope(**kwargs: object) -> Envelope:
    payload = {
        "id": _uid("env"),
        "event_type": "system_health",
        "machine": "google-vm-raj-quant-server",
        "strategy": "hybrid_v2",
        "ts": "2026-08-24T10:06:07Z",
        "health": {
            "tick_rate": 15.2,
            "tick_delay_ms": 0.3,
            "queue_size": 2,
            "queue_wait_ms": 4.1,
            "avg_latency_ms": 6.8,
            "p95_latency_ms": 8.2,
            "p99_latency_ms": 9.1,
            "api_success_pct": 100.0,
            "signal_fill_rate_pct": 98.5,
            "cpu_usage_pct": 12.4,
            "memory_mb": 256.0,
            "status": "STABLE",
        },
    }
    payload.update(kwargs)
    return Envelope(**payload)


def test_system_health_is_not_a_trade() -> None:
    env = _health_envelope()
    assert resolve_dispatch_kind(env) == "system_health"
    # Even if wrapped as kind="trade" with event_type="system_health"
    wrapped = Envelope(
        id=_uid("env"),
        kind="trade",
        event_type="system_health",
        machine="google-vm-raj-quant-server",
        data={"health": {"status": "STABLE"}},
    )
    assert resolve_dispatch_kind(wrapped) == "system_health"


@pytest.mark.asyncio
async def test_system_health_ingest_stores_snapshot(configure_env: None) -> None:
    env = _health_envelope()
    batch = AgentBatch(
        agentId="google-vm-data-agent",
        machine="google-vm-raj-quant-server",
        items=[env],
    )
    ack = await handle_batch(batch, "google-vm-data-agent")
    assert ack.processed == 1
    assert ack.failed == 0

    rows = system_health_repo.query(machine_id="mch-agent-google-vm-raj-quant-server")
    assert len(rows) >= 1
    latest = [r for r in rows if r["event_id"] == env.id][0]
    assert latest["cpu_usage_pct"] == 12.4
    assert latest["tick_rate"] == 15.2
    assert latest["status"] == "STABLE"
    assert latest["avg_latency_ms"] == 6.8
    assert latest["p95_latency_ms"] == 8.2
    assert latest["p99_latency_ms"] == 9.1
    assert latest["queue_size"] == 2
    assert latest["queue_wait_ms"] == 4.1
    assert latest["api_success_pct"] == 100.0
    assert latest["signal_fill_rate_pct"] == 98.5
    assert latest["memory_mb"] == 256.0


def test_system_health_post_batch_endpoint(client: TestClient) -> None:
    env_id = _uid("env")
    payload = {
        "agentId": "google-vm-data-agent",
        "machine": "google-vm-raj-quant-server",
        "items": [
            {
                "id": env_id,
                "event_type": "system_health",
                "machine": "google-vm-raj-quant-server",
                "strategy": "hybrid_v2",
                "ts": "2026-08-24T10:06:07Z",
                "health": {
                    "tick_rate": 20.0,
                    "tick_delay_ms": 0.1,
                    "queue_size": 0,
                    "queue_wait_ms": 1.0,
                    "avg_latency_ms": 5.0,
                    "p95_latency_ms": 7.0,
                    "p99_latency_ms": 8.0,
                    "api_success_pct": 100.0,
                    "signal_fill_rate_pct": 100.0,
                    "cpu_usage_pct": 10.0,
                    "memory_mb": 180.0,
                    "status": "STABLE",
                },
            }
        ],
    }
    resp = client.post("/api/agent/batch", json=payload, headers=agent_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] is True
    assert data["processed"] == 1
    assert data["failed"] == 0


def test_system_health_timestamps_remain_utc() -> None:
    ts = "2026-08-24T10:06:07.123456Z"
    snapshot = {
        "id": _uid("hlth"),
        "machine_id": "mch-agent-google-vm-raj-quant-server",
        "timestamp_utc": ts,
        "tick_rate": 0.0,
        "tick_delay_ms": 0.0,
        "queue_size": 0,
        "queue_wait_ms": 0.0,
        "avg_latency_ms": 0.0,
        "p95_latency_ms": 0.0,
        "p99_latency_ms": 0.0,
        "api_success_pct": 100.0,
        "signal_fill_rate_pct": 0.0,
        "cpu_usage_pct": 5.0,
        "memory_mb": 100.0,
        "status": "STABLE",
    }
    system_health_repo.insert(snapshot)
    results = system_health_repo.query(machine_id="mch-agent-google-vm-raj-quant-server")
    found = [r for r in results if r["id"] == snapshot["id"]][0]
    assert "2026-08-24T10:06:07" in found["timestamp_utc"]
