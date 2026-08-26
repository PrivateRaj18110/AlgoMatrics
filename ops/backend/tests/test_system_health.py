"""Tests for system_health telemetry ingestion, storage, and classification."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.repositories import machines_repo, system_health_repo
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


def test_system_health_rate_fields_and_payload_variants(configure_env: None) -> None:
    env_id = _uid("env")
    env = Envelope(
        id=env_id,
        event_type="system_health",
        machine="google-vm-raj-quant-server",
        data={
            "machine_id": "mch-agent-google-vm-raj-quant-server",
            "generated_at": "2026-08-24T11:16:59Z",
            "health": {
                "tick_rate": 18.5,
                "tick_delay_ms": 0.4,
                "queue_size": 1,
                "queue_wait_ms": 2.5,
                "avg_latency_ms": 7.1,
                "p95_latency_ms": 8.9,
                "p99_latency_ms": 9.5,
                "api_success_rate": 0.99,  # 0..1 fraction
                "signal_fill_rate": 0.95,  # 0..1 fraction
                "cpu_usage": 14.5,
                "memory_mb": 310.0,
                "status": "stable",
            },
        },
    )
    assert resolve_dispatch_kind(env) == "system_health"


@pytest.mark.asyncio
async def test_system_health_idempotency_duplicate_event_id(configure_env: None) -> None:
    env_id = _uid("env")
    env = _health_envelope(id=env_id)
    batch1 = AgentBatch(
        agentId="google-vm-data-agent",
        machine="google-vm-raj-quant-server",
        items=[env],
    )
    ack1 = await handle_batch(batch1, "google-vm-data-agent")
    assert ack1.processed == 1

    # Replay same envelope
    ack2 = await handle_batch(batch1, "google-vm-data-agent")
    assert ack2.processed == 1

    rows = [
        r for r in system_health_repo.query(machine_id="mch-agent-google-vm-raj-quant-server")
        if r.get("event_id") == env_id
    ]
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_system_start_ingestion_and_deduplication(configure_env: None) -> None:
    env_id = _uid("env")
    start_env = Envelope(
        id=env_id,
        event_type="system_start",
        machine="google-vm-raj-quant-server",
        ts="2026-08-24T10:00:00Z",
        data={"machine": "google-vm-raj-quant-server", "status": "online"},
    )
    assert resolve_dispatch_kind(start_env) == "system_start"

    batch = AgentBatch(
        agentId="google-vm-data-agent",
        machine="google-vm-raj-quant-server",
        items=[start_env],
    )
    ack = await handle_batch(batch, "google-vm-data-agent")
    assert ack.processed == 1

    # Duplicate delivery
    ack_dup = await handle_batch(batch, "google-vm-data-agent")
    assert ack_dup.processed == 1


def test_system_health_multiple_machines_filtering() -> None:
    s1 = {
        "id": _uid("hlth"),
        "machine_id": "mch-agent-google-vm-raj-quant-server",
        "timestamp_utc": "2026-08-24T10:00:00Z",
        "cpu_usage_pct": 10.0,
        "status": "STABLE",
    }
    s2 = {
        "id": _uid("hlth"),
        "machine_id": "mch-agent-other-server",
        "timestamp_utc": "2026-08-24T10:00:00Z",
        "cpu_usage_pct": 25.0,
        "status": "DEGRADED",
    }
    system_health_repo.insert(s1)
    system_health_repo.insert(s2)

    g_rows = system_health_repo.query(machine_id="mch-agent-google-vm-raj-quant-server")
    o_rows = system_health_repo.query(machine_id="mch-agent-other-server")
    assert any(r["id"] == s1["id"] for r in g_rows)
    assert not any(r["id"] == s2["id"] for r in g_rows)
    assert any(r["id"] == s2["id"] for r in o_rows)
    assert not any(r["id"] == s1["id"] for r in o_rows)


@pytest.mark.asyncio
async def test_index_option_local_mac_system_start_and_health(configure_env: None) -> None:
    mac_machine = "index-option-local-mac"
    mac_agent = "index-option-local-mac-data-agent"
    expected_mid = "mch-agent-index-option-local-mac"

    # 1. system_start
    start_env = Envelope(
        id=_uid("env"),
        event_type="system_start",
        machine=mac_machine,
        ts="2026-08-24T12:00:00Z",
        data={"machine": mac_machine, "status": "online"},
    )
    batch_start = AgentBatch(
        agentId=mac_agent,
        machine=mac_machine,
        items=[start_env],
    )
    ack_start = await handle_batch(batch_start, mac_agent)
    assert ack_start.accepted is True
    assert ack_start.processed == 1
    assert ack_start.machineId == expected_mid

    mac_info = machines_repo.get(expected_mid)
    assert mac_info is not None
    assert mac_info["status"] == "online"
    assert mac_info["name"] == mac_machine

    # 2. system_health
    health_env = Envelope(
        id=_uid("env"),
        event_type="system_health",
        machine=mac_machine,
        ts="2026-08-24T12:01:00Z",
        data={
            "machine_id": expected_mid,
            "status": "STABLE",
            "cpu_usage_pct": 14.5,
            "memory_mb": 420.0,
            "avg_latency_ms": 3.2,
            "queue_size": 0,
        },
    )
    batch_health = AgentBatch(
        agentId=mac_agent,
        machine=mac_machine,
        items=[health_env],
    )
    ack_health = await handle_batch(batch_health, mac_agent)
    assert ack_health.accepted is True
    assert ack_health.processed == 1

    health_records = system_health_repo.query(machine_id=expected_mid)
    assert len(health_records) >= 1
    latest = health_records[0]
    assert latest["machine_id"] == expected_mid
    assert latest["agent_id"] == mac_agent
    assert latest["status"] == "STABLE"
    assert latest["cpu_usage_pct"] == 14.5


