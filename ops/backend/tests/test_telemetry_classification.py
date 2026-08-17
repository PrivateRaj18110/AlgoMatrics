"""Closed-trade classification: only explicit trades enter the blotter."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path
import subprocess
import sys
import textwrap
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.schemas.agent import Envelope
from app.services.telemetry_classification import resolve_dispatch_kind
from tests.conftest import DASHBOARD_TOKEN, agent_headers
from tests.test_ws_auth import _subprotocol

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def _env(**kwargs: object) -> Envelope:
    payload = {"id": _uid("env"), "kind": "event", "machine": "m1", "strategy": "s1", "data": {}}
    payload.update(kwargs)
    return Envelope(**payload)


# --------------------------------------------------------------------------- #
# Pure classification
# --------------------------------------------------------------------------- #
def test_legacy_kind_trade_is_still_a_trade() -> None:
    assert resolve_dispatch_kind(_env(kind="trade")) == "trade"


def test_heartbeat_is_not_a_trade() -> None:
    assert resolve_dispatch_kind(_env(kind="heartbeat")) == "heartbeat"
    assert resolve_dispatch_kind(_env(kind="trade", event_type="heartbeat")) == "heartbeat"
    assert resolve_dispatch_kind(_env(kind="trade", data={"event_type": "heartbeat"})) == "heartbeat"


def test_strategy_status_is_not_a_trade() -> None:
    assert resolve_dispatch_kind(_env(kind="strategy_status")) == "strategy_status"
    assert resolve_dispatch_kind(_env(kind="trade", event_type="strategy_status")) == "strategy_status"


def test_system_status_is_not_a_trade() -> None:
    assert resolve_dispatch_kind(_env(kind="system_status")) == "system_status"
    assert resolve_dispatch_kind(_env(kind="trade", data={"event_type": "system_status"})) == "system_status"


def test_order_is_not_a_closed_trade() -> None:
    assert resolve_dispatch_kind(_env(kind="order")) == "order"
    assert resolve_dispatch_kind(_env(kind="trade", event_type="order", data={"direction": "long"})) == "order"


def test_google_trade_closed_maps_to_trade() -> None:
    assert resolve_dispatch_kind(_env(kind="event", source_event_type="trade_closed")) == "trade"
    assert resolve_dispatch_kind(_env(event_type="trade", kind=None)) == "trade"


def test_direction_symbol_do_not_infer_trade() -> None:
    env = _env(kind="heartbeat", data={"direction": "long", "symbol": "NIFTY", "strategy": "x", "order": {}})
    assert resolve_dispatch_kind(env) == "heartbeat"


def test_data_agent_envelope_parses_without_kind() -> None:
    env = Envelope(
        event_id="da-1",
        event_type="heartbeat",
        machine_id="google-vm-raj-quantiser",
        payload={"cpu": 1.0},
    )
    assert env.id == "da-1"
    assert env.kind == "heartbeat"
    assert env.machine == "google-vm-raj-quantiser"
    assert env.data == {"cpu": 1.0}
    assert resolve_dispatch_kind(env) == "heartbeat"


# --------------------------------------------------------------------------- #
# HTTP ingest (mock mode: events + websocket; trades persist only with a DB)
# --------------------------------------------------------------------------- #
def test_mixed_batch_routes_non_trades_to_events(client: TestClient) -> None:
    machine = f"cls-{uuid4().hex[:8]}"
    items = [
        {"id": _uid("hb"), "kind": "trade", "event_type": "heartbeat", "machine": machine,
         "strategy": "unknown", "data": {"cpu": 9.0, "ram": 10.0, "health": "healthy"}},
        {"id": _uid("ss"), "kind": "strategy_status", "machine": machine, "strategy": "alpha",
         "data": {"status": "running"}},
        {"id": _uid("or"), "kind": "order", "machine": machine, "strategy": "alpha",
         "data": {"side": "buy", "symbol": "NIFTY", "status": "submitted"}},
        {"id": _uid("sy"), "kind": "system_status", "machine": machine, "strategy": "agent",
         "data": {"transportState": "connected"}},
        {"id": _uid("tr"), "kind": "trade", "machine": machine, "strategy": "alpha",
         "data": {"symbol": "NIFTY", "direction": "long", "action": "close",
                  "entry": 100.5, "exit": 101.0, "quantity": 1, "pnl": 12.5,
                  "latencyMs": 8, "durationSec": 42}},
    ]
    response = client.post(
        "/api/agent/batch",
        json={"agentId": "agent-cls", "machine": machine, "items": items},
        headers=agent_headers(),
    )
    assert response.status_code == 200, response.text
    assert response.json()["rejected"] == 0
    assert response.json()["processed"] == 5

    events = client.get("/api/events?limit=400").json()
    ours = [row for row in events if row.get("source", "").startswith(machine)]
    types = {row["eventType"] for row in ours}
    assert "strategy_status" in types
    assert "order" in types
    assert "system_status" in types
    assert "trade" in types
    assert sum(1 for row in ours if row["eventType"] == "trade") == 1
    assert sum(1 for row in ours if row["eventType"] == "order") == 1
    assert sum(1 for row in ours if row["eventType"] == "heartbeat") == 0

    machines = client.get("/api/machines").json()
    host = next(m for m in machines if m["name"] == machine)
    assert host["lastHeartbeat"]


def test_websocket_heartbeat_does_not_emit_trade(client: TestClient) -> None:
    machine = f"cls-ws-hb-{uuid4().hex[:8]}"
    with client.websocket_connect("/api/ws", subprotocols=_subprotocol(DASHBOARD_TOKEN)) as ws:
        assert ws.receive_json()["type"] == "machines"
        response = client.post(
            "/api/agent/batch",
            json={
                "agentId": "agent-cls",
                "machine": machine,
                "items": [{
                    "id": _uid("hb"), "kind": "heartbeat", "machine": machine,
                    "strategy": "unknown", "data": {"cpu": 4.0, "health": "healthy"},
                }],
            },
            headers=agent_headers(),
        )
        assert response.status_code == 200, response.text
        frames = [ws.receive_json()["type"] for _ in range(3)]
    assert "trade" not in frames


def test_websocket_order_does_not_emit_trade(client: TestClient) -> None:
    machine = f"cls-ws-or-{uuid4().hex[:8]}"
    with client.websocket_connect("/api/ws", subprotocols=_subprotocol(DASHBOARD_TOKEN)) as ws:
        assert ws.receive_json()["type"] == "machines"
        response = client.post(
            "/api/agent/batch",
            json={
                "agentId": "agent-cls",
                "machine": machine,
                "items": [{
                    "id": _uid("or"), "kind": "order", "machine": machine,
                    "strategy": "alpha", "data": {"side": "buy", "symbol": "NIFTY"},
                }],
            },
            headers=agent_headers(),
        )
        assert response.status_code == 200, response.text
        frame = ws.receive_json()
    assert frame["type"] == "event"
    assert frame["payload"]["eventType"] == "order"


def test_websocket_trade_emits_trade(client: TestClient) -> None:
    machine = f"cls-ws-tr-{uuid4().hex[:8]}"
    with client.websocket_connect("/api/ws", subprotocols=_subprotocol(DASHBOARD_TOKEN)) as ws:
        assert ws.receive_json()["type"] == "machines"
        response = client.post(
            "/api/agent/batch",
            json={
                "agentId": "agent-cls",
                "machine": machine,
                "items": [{
                    "id": _uid("tr"), "kind": "trade", "machine": machine, "strategy": "alpha",
                    "data": {"symbol": "NIFTY", "direction": "long", "action": "close",
                             "entry": 10.0, "exit": 11.0, "quantity": 1, "pnl": 5.0},
                }],
            },
            headers=agent_headers(),
        )
        assert response.status_code == 200, response.text
        types = [ws.receive_json()["type"] for _ in range(2)]
    assert "trade" in types
    assert "event" in types


def test_agent_trades_endpoint_does_not_coerce_heartbeat(client: TestClient) -> None:
    machine = f"cls-hb-{uuid4().hex[:8]}"
    with client.websocket_connect("/api/ws", subprotocols=_subprotocol(DASHBOARD_TOKEN)) as ws:
        assert ws.receive_json()["type"] == "machines"
        response = client.post(
            "/api/agent/trades",
            json={
                "id": _uid("hb-path"),
                "kind": "heartbeat",
                "machine": machine,
                "strategy": "unknown",
                "data": {"cpu": 3.0, "health": "healthy"},
            },
            headers=agent_headers(),
        )
        assert response.status_code == 200, response.text
        assert response.json()["kind"] == "heartbeat"
        frames = [ws.receive_json()["type"] for _ in range(3)]
    assert "trade" not in frames


# --------------------------------------------------------------------------- #
# Durable blotter (real SQLite) — /api/trades must not contain telemetry junk
# --------------------------------------------------------------------------- #
FLEET_TOKEN = "classification-fleet-token"
HEADERS = {"X-Raj-Agent-Token": FLEET_TOKEN, "X-Raj-Agent-Id": "agent-cls-01"}


def _environment(database_url: str) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(BACKEND_DIR), env.get("PYTHONPATH", "")) if part
    )
    env["RAJ_AGENT_TOKEN"] = FLEET_TOKEN
    env["RAJ_DASHBOARD_TOKEN"] = "classification-dashboard-token"
    env.pop("RAJ_AGENT_TOKENS", None)
    env.pop("ENVIRONMENT", None)
    env["DATABASE_URL"] = database_url
    return env


def _run_backend(code: str, database_url: str) -> dict:
    script = textwrap.dedent(
        """
        import json
        from fastapi.testclient import TestClient
        from main import app
        HEADERS = %r
        """
        % (HEADERS,)
    ) + "\n" + textwrap.dedent(code)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=BACKEND_DIR,
        env=_environment(database_url),
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.fixture
def database() -> Iterator[str]:
    db_dir = BACKEND_DIR / ".pytest_sqlite"
    db_dir.mkdir(exist_ok=True)
    db_path = db_dir / f"classify-{uuid4().hex}.db"
    url = f"sqlite:///{db_path.as_posix()}"
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=_environment(url),
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    try:
        yield url
    finally:
        db_path.unlink(missing_ok=True)


def test_mixed_batch_persists_exactly_one_trade(database: str) -> None:
    result = _run_backend(
        """
        from uuid import uuid4
        machine = "google-vm-raj-quantiser"
        items = [
            {"id": "e-hb", "kind": "trade", "event_type": "heartbeat", "machine": machine,
             "strategy": "unknown", "data": {"cpu": 1, "health": "healthy"}},
            {"id": "e-st", "kind": "strategy_status", "machine": machine, "strategy": "alpha",
             "data": {"status": "running"}},
            {"id": "e-or", "kind": "order", "machine": machine, "strategy": "alpha",
             "data": {"side": "buy", "symbol": "NIFTY"}},
            {"id": "e-sy", "kind": "system_status", "machine": machine, "strategy": "agent",
             "data": {"transportState": "connected"}},
            {"id": "e-tr", "kind": "trade", "source_event_type": "trade_closed", "machine": machine,
             "strategy": "alpha",
             "data": {"symbol": "NIFTY", "direction": "long", "action": "close",
                      "entry": 100.5, "exit": 101.25, "quantity": 2, "pnl": 15.0,
                      "latencyMs": 11, "durationSec": 30}},
        ]
        with TestClient(app) as c:
            first = c.post("/api/agent/batch", json={"agentId": "a1", "machine": machine, "items": items},
                           headers=HEADERS)
            second = c.post("/api/agent/batch", json={"agentId": "a1", "machine": machine, "items": items},
                            headers=HEADERS)
            trades = c.get("/api/trades").json()
            events = c.get("/api/events?limit=400").json()
            ours = [t for t in trades if t["machine"] == machine]
            ev = [e for e in events if machine in (e.get("source") or "")]
        print(json.dumps({
            "status": first.status_code,
            "processed": first.json()["processed"],
            "dup_processed": second.json()["processed"],
            "dup_duplicate": second.json()["duplicate"],
            "trades": len(ours),
            "trade": ours[0] if ours else None,
            "event_types": sorted({e["eventType"] for e in ev if e.get("eventType")}),
            "order_events": sum(1 for e in ev if e.get("eventType") == "order"),
            "trade_events": sum(1 for e in ev if e.get("eventType") == "trade"),
        }))
        """,
        database,
    )
    assert result["status"] == 200
    assert result["processed"] == 5
    assert result["dup_processed"] == 0
    assert result["dup_duplicate"] == 5
    assert result["trades"] == 1
    trade = result["trade"]
    assert trade["strategy"] == "alpha"
    assert trade["entry"] == 100.5
    assert trade["exit"] == 101.25
    assert trade["pnl"] == 15.0
    assert trade["durationSec"] == 30
    assert trade["status"] == "closed"
    assert trade["symbol"] == "NIFTY"
    assert result["order_events"] == 1
    assert result["trade_events"] == 1
    assert "strategy_status" in result["event_types"]
    assert "system_status" in result["event_types"]
    assert "order" in result["event_types"]


def test_api_events_contains_generic_telemetry_not_only_trades(database: str) -> None:
    result = _run_backend(
        """
        machine = "cls-events-host"
        items = [
            {"id": "g-1", "kind": "system_status", "machine": machine, "strategy": "agent",
             "data": {"transportState": "connected"}},
            {"id": "g-2", "kind": "order", "machine": machine, "strategy": "alpha",
             "data": {"status": "rejected", "symbol": "BANKNIFTY"}},
        ]
        with TestClient(app) as c:
            c.post("/api/agent/batch", json={"agentId": "a1", "machine": machine, "items": items},
                   headers=HEADERS)
            events = c.get("/api/events?limit=400").json()
            trades = [t for t in c.get("/api/trades").json() if t["machine"] == machine]
            types = {e["eventType"] for e in events if machine in (e.get("source") or "")}
        print(json.dumps({"types": sorted(types), "trades": len(trades)}))
        """,
        database,
    )
    assert "system_status" in result["types"]
    assert "order" in result["types"]
    assert result["trades"] == 0
