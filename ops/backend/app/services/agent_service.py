"""Agent ingestion service — server side of the Raj Local Agent contract.

This is the live counterpart to the mock publisher: instead of jittering fake
telemetry, it folds *real* agent data into the repositories and broadcasts it
over the websocket, so the dashboard shows live machines, events, trades and
logs with no UI changes.

Persistence + idempotency (DB mode)
-----------------------------------
Each envelope is processed inside a single ``unit_of_work()`` transaction. The
first step reserves the envelope id (``reserve_envelope``); a duplicate (the
agent delivers at-least-once from its durable queue) is skipped entirely — no
rows, no broadcast. Heartbeats/metrics update the machine record; ``metrics``
snapshots and custom ``metric()`` calls also append to the metrics time-series;
trades append to the blotter. In mock mode (no ``DATABASE_URL``) the unit of
work and dedup are no-ops and trade/metric persistence is skipped, preserving
the original in-memory behavior exactly.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.realtime.broadcaster import broadcaster
from app.repositories import (
    events_repo,
    logs_repo,
    machines_repo,
    metrics_repo,
    reserve_envelope,
    trades_repo,
    unit_of_work,
)
from app.schemas.agent import AgentAck, AgentBatch, AgentHeartbeat, AgentRegister, Envelope

# Machine ids registered by a live agent. The mock publisher consults this set so
# it never overwrites real telemetry with jittered demo values.
LIVE_MACHINE_IDS: set[str] = set()

# Host-metric fields persisted from a full ``metrics`` snapshot (name, unit).
_HOST_METRIC_FIELDS = (("cpu", "%"), ("ram", "%"), ("disk", "%"),
                       ("internetMs", "ms"), ("brokerPingMs", "ms"))

# Trade lifecycle action -> blotter status (other actions aren't blotter rows).
_TRADE_STATUS = {"open": "open", "close": "closed", "cancelled": "cancelled", "rejected": "cancelled"}

def _next_id(prefix: str) -> str:
    return f"{prefix}-agent-{uuid4().hex}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ack(kind: str, processed: int = 1, machine_id: str | None = None) -> AgentAck:
    return AgentAck(accepted=True, received=_now_iso(), kind=kind,
                    processed=processed, machineId=machine_id)


def machine_id_for(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "unknown").lower()).strip("-")
    return f"mch-agent-{slug or 'unknown'}"


def _status_from_health(health: str | None) -> str:
    return {"healthy": "online", "degraded": "degraded", "critical": "degraded"}.get(
        (health or "healthy").lower(), "online"
    )


# --------------------------------------------------------------------------- #
# Broadcasting helpers
# --------------------------------------------------------------------------- #
def _public_event(event: dict) -> dict:
    """The websocket/API shape — internal keys (envelope_id, machine_id) stripped."""
    return {"id": event["id"], "time": event["time"], "category": event["category"],
            "severity": event["severity"], "source": event["source"], "message": event["message"]}


async def _broadcast_machines() -> None:
    await broadcaster.broadcast({"type": "machines", "payload": machines_repo.list()})


async def _emit_event(category: str, severity: str, source: str, message: str,
                      *, envelope_id: str | None = None, machine_id: str | None = None) -> dict:
    event = {
        "id": _next_id("evt"), "time": _now_iso(), "category": category,
        "severity": severity, "source": source, "message": message,
        "envelope_id": envelope_id, "machine_id": machine_id,
    }
    events_repo.prepend(event)
    await broadcaster.broadcast({"type": "event", "payload": _public_event(event)})
    return event


def _log(source: str, level: str, logger: str, message: str,
         *, envelope_id: str | None = None, machine_id: str | None = None) -> None:
    logs_repo.prepend({
        "id": _next_id("log"), "time": _now_iso(),
        "source": source, "level": level, "logger": logger, "message": message,
        "envelope_id": envelope_id, "machine_id": machine_id,
    })


# --------------------------------------------------------------------------- #
# Registration + telemetry handlers
# --------------------------------------------------------------------------- #
async def handle_register(p: AgentRegister) -> AgentAck:
    mid = machine_id_for(p.machine)
    machine = {
        "id": mid, "name": p.machine, "location": p.location or "Live agent",
        "provider": p.provider or "Raj Local Agent", "status": "online",
        "cpu": 0.0, "ram": 0.0, "disk": 0.0, "temperatureC": None,
        "internetMs": 0.0, "brokerPingMs": 0.0, "pythonStatus": "online",
        "uptimeSec": 0, "lastHeartbeat": _now_iso(), "strategyCount": 0,
        "live": True, "agentId": p.agentId,
    }
    machines_repo.upsert(machine)
    LIVE_MACHINE_IDS.add(mid)
    await _emit_event("machine", "info", p.machine,
                      f"Agent registered (v{p.sdkVersion or '?'}, Python {p.python or '?'})",
                      machine_id=mid)
    _log("system", "info", "raj.agent", f"register {p.machine} -> {mid}", machine_id=mid)
    await _broadcast_machines()
    return _ack("register", machine_id=mid)


async def _apply_machine_telemetry(machine: str, t: dict[str, Any]) -> str:
    """Merge a heartbeat/metrics snapshot into the machine record."""
    mid = machine_id_for(machine)
    if mid not in LIVE_MACHINE_IDS:
        # First contact via telemetry (no explicit register): create the host.
        await handle_register(AgentRegister(agentId=t.get("agentId", mid), machine=machine))
    changes = {
        "cpu": round(float(t.get("cpu", 0.0)), 1),
        "ram": round(float(t.get("ram", 0.0)), 1),
        "disk": round(float(t.get("disk", 0.0)), 1),
        "internetMs": round(float(t.get("internetMs", 0.0)), 1),
        "brokerPingMs": round(float(t.get("brokerPingMs", t.get("latencyMs", 0.0))), 1),
        "uptimeSec": int(t.get("uptimeSec", 0)),
        "pythonStatus": "online",
        "lastHeartbeat": t.get("ts") or _now_iso(),
        "status": _status_from_health(t.get("health")),
    }
    if t.get("strategyCount") is not None:
        changes["strategyCount"] = int(t["strategyCount"])
    machines_repo.update(mid, changes)
    return mid


async def handle_heartbeat(p: AgentHeartbeat) -> AgentAck:
    mid = await _apply_machine_telemetry(p.machine, p.model_dump())
    await _broadcast_machines()
    return _ack("heartbeat", machine_id=mid)


async def _handle_metrics(machine: str, data: dict[str, Any]) -> str:
    mid = await _apply_machine_telemetry(machine, data)
    await _broadcast_machines()
    return mid


def _persist_host_metrics(machine: str, mid: str | None, env_id: str | None, data: dict[str, Any]) -> None:
    """Append a full host-metrics snapshot to the metrics time-series."""
    ts = _now_iso()
    for name, unit in _HOST_METRIC_FIELDS:
        value = data.get(name)
        if name == "brokerPingMs" and value is None:
            value = data.get("latencyMs")
        if value is None:
            continue
        metrics_repo.insert({
            "envelope_id": env_id, "time": ts, "machine": machine, "machine_id": mid,
            "strategy": None, "name": name, "value": value, "unit": unit,
        })


async def _handle_event(machine: str, strategy: str, data: dict[str, Any],
                        env_id: str | None = None, mid: str | None = None) -> None:
    await _emit_event(
        data.get("category", "strategy"),
        data.get("severity", "info"),
        f"{machine} · {strategy}",
        data.get("message", ""),
        envelope_id=env_id, machine_id=mid,
    )


async def _handle_error(machine: str, strategy: str, data: dict[str, Any],
                        env_id: str | None = None, mid: str | None = None) -> None:
    await _emit_event("system", "critical", f"{machine} · {strategy}",
                      f"Python exception: {data.get('message', '')}",
                      envelope_id=env_id, machine_id=mid)
    _log("python", "error", strategy, data.get("message", ""), envelope_id=env_id, machine_id=mid)


async def _handle_trade(machine: str, strategy: str, data: dict[str, Any],
                        env_id: str | None = None, mid: str | None = None,
                        account: str | None = None) -> None:
    action = data.get("action", "close")
    pnl = float(data.get("pnl", 0.0))
    direction = str(data.get("direction", "")).upper()
    severity = "warning" if action in ("rejected", "cancelled") else "info"
    await _emit_event("trade", severity, f"{machine} · {strategy}",
                      f"Trade {action} {direction} {data.get('symbol', '')} · PnL {pnl:+.0f}",
                      envelope_id=env_id, machine_id=mid)
    _log("strategy", "info", strategy,
         f"trade() {data.get('symbol', '')} {action} pnl={pnl}", envelope_id=env_id, machine_id=mid)
    _persist_trade(machine, strategy, data, env_id, mid, account)


def _persist_trade(machine: str, strategy: str, data: dict[str, Any],
                   env_id: str | None, mid: str | None, account: str | None) -> None:
    """Append a trade to the blotter (open/close/cancelled/rejected only)."""
    action = str(data.get("action", "close"))
    status = _TRADE_STATUS.get(action)
    if status is None:  # modify / pending are not blotter rows
        return
    trades_repo.insert({
        "id": _next_id("trd"), "envelope_id": env_id, "time": _now_iso(),
        "strategy": strategy, "machine": machine, "machine_id": mid,
        "broker": data.get("broker") or "", "account": account or "",
        "symbol": data.get("symbol", ""), "direction": str(data.get("direction", "long")).lower(),
        "action": action, "entry": data.get("entry", 0.0), "exit": data.get("exit"),
        "quantity": data.get("quantity", 0.0), "pnl": data.get("pnl", 0.0),
        "latencyMs": data.get("latencyMs", 0.0), "durationSec": data.get("durationSec", 0),
        "status": status,
    })


async def _handle_start(machine: str, strategy: str, data: dict[str, Any],
                        env_id: str | None = None, mid: str | None = None) -> None:
    await _emit_event("strategy", "info", f"{machine} · {strategy}",
                      data.get("message", "Strategy started"), envelope_id=env_id, machine_id=mid)
    _log("strategy", "info", strategy, f"start() on {machine}", envelope_id=env_id, machine_id=mid)


async def _handle_stop(machine: str, strategy: str, data: dict[str, Any],
                       env_id: str | None = None, mid: str | None = None) -> None:
    await _emit_event("strategy", "warning", f"{machine} · {strategy}",
                      data.get("message", "Strategy stopped"), envelope_id=env_id, machine_id=mid)
    _log("strategy", "info", strategy, f"stop() on {machine}", envelope_id=env_id, machine_id=mid)


def _handle_log(machine: str, strategy: str, data: dict[str, Any],
                env_id: str | None = None, mid: str | None = None) -> None:
    _log(data.get("source", "strategy"), data.get("level", "info"),
         data.get("logger", strategy), data.get("message", ""), envelope_id=env_id, machine_id=mid)


def _handle_metric(machine: str, strategy: str, data: dict[str, Any],
                   env_id: str | None = None, mid: str | None = None) -> None:
    _log("strategy", "debug", strategy,
         f"metric() {data.get('name')}={data.get('value')}{data.get('unit') or ''}",
         envelope_id=env_id, machine_id=mid)
    metrics_repo.insert({
        "envelope_id": env_id, "time": _now_iso(), "machine": machine, "machine_id": mid,
        "strategy": strategy, "name": data.get("name", ""), "value": data.get("value", 0.0),
        "unit": data.get("unit"),
    })


def _handle_position(machine: str, strategy: str, data: dict[str, Any],
                     env_id: str | None = None, mid: str | None = None) -> None:
    _log("strategy", "info", strategy,
         f"position() {data.get('direction')} {data.get('symbol')} "
         f"qty={data.get('quantity')} uPnL={data.get('unrealizedPnl')}",
         envelope_id=env_id, machine_id=mid)


# --------------------------------------------------------------------------- #
# Dispatch (single envelope, transactional + idempotent) + batch
# --------------------------------------------------------------------------- #
async def _dispatch_inner(env: Envelope) -> None:
    kind, machine, strategy, data = env.kind, env.machine, env.strategy, env.data
    env_id = env.id
    mid = machine_id_for(machine) if machine and machine != "unknown" else None
    if kind in ("heartbeat", "metrics"):
        await _handle_metrics(machine, {**data, "agentId": data.get("agentId")})
        if kind == "metrics":
            _persist_host_metrics(machine, mid, env_id, data)
    elif kind == "metric":
        _handle_metric(machine, strategy, data, env_id, mid)
    elif kind == "event":
        await _handle_event(machine, strategy, data, env_id, mid)
    elif kind == "error":
        await _handle_error(machine, strategy, data, env_id, mid)
    elif kind == "trade":
        await _handle_trade(machine, strategy, data, env_id, mid, env.account)
    elif kind == "position":
        _handle_position(machine, strategy, data, env_id, mid)
    elif kind == "start":
        await _handle_start(machine, strategy, data, env_id, mid)
    elif kind == "stop":
        await _handle_stop(machine, strategy, data, env_id, mid)
    elif kind == "log":
        _handle_log(machine, strategy, data, env_id, mid)


async def _dispatch(env: Envelope) -> None:
    """Process one envelope in a single transaction, skipping duplicates."""
    with unit_of_work():
        if not reserve_envelope(env.id, env.kind):
            return  # already processed (at-least-once delivery) — no side effects
        await _dispatch_inner(env)


async def handle_batch(batch: AgentBatch) -> AgentAck:
    for env in batch.items:
        try:
            await _dispatch(env)
        except Exception:  # one bad item must not fail the whole batch
            continue
    mid = machine_id_for(batch.machine)
    return _ack("batch", processed=len(batch.items), machine_id=mid)


# Thin wrappers for the per-kind direct endpoints — routed through the same
# transactional, idempotent dispatch path as the batch.
def _as_envelope(kind: str, env: Envelope) -> Envelope:
    return Envelope(kind=kind, id=env.id, machine=env.machine, strategy=env.strategy,
                    account=env.account, data=env.data)


async def handle_events(env: Envelope) -> AgentAck:
    await _dispatch(_as_envelope("event", env))
    return _ack("event")


async def handle_metrics_endpoint(env: Envelope) -> AgentAck:
    await _dispatch(_as_envelope("metrics", env))
    return _ack("metrics", machine_id=machine_id_for(env.machine))


async def handle_trades_endpoint(env: Envelope) -> AgentAck:
    await _dispatch(_as_envelope("trade", env))
    return _ack("trade")


async def handle_logs_endpoint(env: Envelope) -> AgentAck:
    await _dispatch(_as_envelope("log", env))
    return _ack("log")
