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

import logging
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from app.realtime.broadcaster import broadcaster
from app.repositories import (
    dead_letter_repo,
    events_repo,
    logs_repo,
    machines_repo,
    metrics_repo,
    reserve_envelope,
    sessions_repo,
    sync_state_repo,
    system_health_repo,
    trades_repo,
    unit_of_work,
)
from app.schemas.agent import (
    AgentAck,
    AgentBatch,
    AgentHeartbeat,
    AgentRegister,
    Envelope,
    EnvelopeOutcome,
)
from app.services.telemetry_classification import resolve_dispatch_kind

# Ingest observability. Never logs payload bodies or credentials — only
# identifiers, kinds and outcomes.
log = logging.getLogger("ops.ingest")

# Machine ids registered by a live agent. The mock publisher consults this set so
# it never overwrites real telemetry with jittered demo values.
LIVE_MACHINE_IDS: set[str] = set()

# Host-metric fields persisted from a full ``metrics`` snapshot (name, unit).
_HOST_METRIC_FIELDS = (("cpu", "%"), ("ram", "%"), ("disk", "%"),
                       ("internetMs", "ms"), ("brokerPingMs", "ms"))

# Trade lifecycle action -> blotter status (other actions aren't blotter rows).
_TRADE_STATUS = {"open": "open", "close": "closed", "cancelled": "cancelled", "rejected": "cancelled"}

# Envelope kinds this service knows how to route. Anything else is a permanent
# rejection: redelivering it would fail identically, so it is dead-lettered
# rather than retried forever.
KNOWN_KINDS = frozenset({
    "heartbeat", "metrics", "metric", "event", "error",
    "trade", "position", "start", "stop", "log",
    # Phase 3 vocabulary. Observational telemetry only; no AWS -> Google
    # control path and no broker/order execution authority.
    "system_status", "strategy_status", "signal", "order", "fill",
    "pnl", "risk", "sync_status", "recovery", "system_health",
})


# Upper bound on a failure reason echoed back to the agent and stored on the
# dead letter. Pydantic validation errors can run to hundreds of characters and
# quote the offending payload; the first line is what identifies the problem.
_REASON_LIMIT = 300


def _short_reason(text: str) -> str:
    collapsed = " ".join(str(text).split())
    return collapsed[:_REASON_LIMIT] + "…" if len(collapsed) > _REASON_LIMIT else collapsed


class Outcome(str, Enum):
    """What actually happened to one envelope.

    The distinction that matters is REJECTED vs FAILED:

    * ``REJECTED`` — permanently unprocessable (unknown kind, malformed
      payload). Retrying cannot help, so it is dead-lettered and the agent is
      told to stop holding it.
    * ``FAILED`` — transient (the database is unavailable). The agent MUST keep
      it and retry; dead-lettering it would destroy recoverable data.
    """

    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"
    FAILED = "failed"

def _next_id(prefix: str) -> str:
    return f"{prefix}-agent-{uuid4().hex}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
    """The websocket/API shape — internal keys stripped, safe metadata kept."""
    return {
        "id": event["id"], "time": event["time"], "category": event["category"],
        "severity": event["severity"], "source": event["source"], "message": event["message"],
        "machineId": event.get("machine_id"), "eventType": event.get("event_type"),
        "strategy": event.get("strategy"), "symbol": event.get("symbol"),
        "sessionId": event.get("session_id"), "sequenceId": event.get("sequence_id"),
        "payloadSummary": event.get("payload_summary"),
        "sourceEventType": event.get("source_event_type"),
    }


async def _broadcast_machines() -> None:
    await broadcaster.broadcast({"type": "machines", "payload": machines_repo.list()})


async def _emit_event(
    category: str,
    severity: str,
    source: str,
    message: str,
    *,
    envelope_id: str | None = None,
    machine_id: str | None = None,
    event_type: str | None = None,
    strategy: str | None = None,
    symbol: str | None = None,
    session_id: str | None = None,
    sequence_id: int | None = None,
    payload_summary: str | None = None,
    event_time: str | None = None,
    source_event_type: str | None = None,
) -> dict:
    event = {
        "id": _next_id("evt"), "time": event_time or _now_iso(), "category": category,
        "severity": severity, "source": source, "message": message,
        "envelope_id": envelope_id, "machine_id": machine_id,
        "event_type": event_type, "strategy": strategy, "symbol": symbol,
        "session_id": session_id, "sequence_id": sequence_id,
        "payload_summary": payload_summary,
        "source_event_type": source_event_type,
        "machineId": machine_id, "eventType": event_type,
        "sessionId": session_id, "sequenceId": sequence_id,
        "payloadSummary": payload_summary,
        "sourceEventType": source_event_type,
        "receivedAt": _now_iso(),
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


def _public_trade(trade: dict) -> dict:
    return {
        "id": trade["id"], "time": trade["time"], "strategy": trade.get("strategy", ""),
        "machine": trade.get("machine", ""), "broker": trade.get("broker", ""),
        "account": trade.get("account", ""), "symbol": trade.get("symbol", ""),
        "direction": trade.get("direction", "long"), "entry": trade.get("entry", 0.0),
        "exit": trade.get("exit"), "quantity": trade.get("quantity", 0.0),
        "pnl": trade.get("pnl", 0.0), "latencyMs": trade.get("latencyMs", 0.0),
        "durationSec": trade.get("durationSec", 0), "status": trade.get("status", "closed"),
    }


async def _broadcast_trade(trade: dict) -> None:
    await broadcaster.broadcast({"type": "trade", "payload": _public_trade(trade)})


def _payload_summary(data: dict[str, Any], *, limit: int = 240) -> str | None:
    """Small, deterministic, dashboard-safe preview of non-secret fields."""
    allowed = (
        "status", "state", "action", "symbol", "side", "direction", "quantity",
        "price", "avgPrice", "pnl", "realizedPnl", "unrealizedPnl", "reason",
        "queueDepth", "oldestPendingAgeSec", "transportState",
        "eventsRecovered", "eodBacklog", "recoveryState",
        "event_type", "source_event_type",
    )
    pairs = [
        f"{key}={data[key]}"
        for key in allowed
        if key in data and data[key] is not None and not isinstance(data[key], (dict, list))
    ]
    if not pairs:
        return None
    text = ", ".join(pairs)
    return text[:limit] + "…" if len(text) > limit else text


def _symbol(data: dict[str, Any]) -> str | None:
    value = data.get("symbol") or data.get("instrument") or data.get("ticker")
    return str(value) if value else None


def _touch_machine(mid: str | None, changes: dict[str, Any]) -> None:
    if not mid:
        return
    try:
        machines_repo.update(mid, changes)
    except Exception:
        log.exception("machine current-state update failed machine_id=%s", mid)


# --------------------------------------------------------------------------- #
# Registration + telemetry handlers
# --------------------------------------------------------------------------- #
async def handle_register(p: AgentRegister) -> AgentAck:
    mid = machine_id_for(p.machine)
    machine = {
        "id": mid, "name": p.machine, "location": p.location or "Live agent",
        "provider": p.provider or "Raj Local Agent", "status": "online",
        "temperatureC": None,
        "pythonStatus": "online",
        "lastHeartbeat": _now_iso(), "strategyCount": None,
        "live": True, "agentId": p.agentId, "agentVersion": p.sdkVersion,
        "hostname": p.hostname or p.machine, "environment": p.environment or "",
        "transportState": "registered",
    }
    machines_repo.upsert(machine)
    LIVE_MACHINE_IDS.add(mid)
    await _emit_event("machine", "info", p.machine,
                      f"Agent registered (v{p.sdkVersion or '?'}, Python {p.python or '?'})",
                      machine_id=mid, event_type="agent_registered",
                      payload_summary=_payload_summary({"status": "registered"}))
    _log("system", "info", "raj.agent", f"register {p.machine} -> {mid}", machine_id=mid)
    await _broadcast_machines()
    return _ack("register", machine_id=mid)


async def _apply_machine_telemetry(machine: str, t: dict[str, Any]) -> str:
    """Merge a heartbeat/metrics snapshot into the machine record."""
    mid = machine_id_for(machine)
    if mid not in LIVE_MACHINE_IDS:
        # First contact via telemetry (no explicit register): create the host.
        # `or mid` rather than a dict default: callers pass an explicit
        # "agentId": None when the envelope carries no agent id, and `.get`'s
        # default only applies to a *missing* key. Without the coalesce this
        # raised a ValidationError, which the old `except: continue` in
        # handle_batch swallowed — so the first heartbeat from a host whose
        # register call had not landed was silently dropped and the machine
        # never appeared on the dashboard.
        await handle_register(AgentRegister(agentId=t.get("agentId") or mid, machine=machine))
    def _reported_float(*keys: str) -> float | None:
        for key in keys:
            if key in t and t[key] is not None:
                return round(float(t[key]), 1)
        return None

    changes: dict[str, Any] = {
        "pythonStatus": "online",
        "lastHeartbeat": t.get("ts") or _now_iso(),
        "status": _status_from_health(t.get("health")),
    }
    cpu = _reported_float("cpu")
    ram = _reported_float("ram")
    disk = _reported_float("disk")
    internet = _reported_float("internetMs")
    broker_ping = _reported_float("brokerPingMs", "latencyMs")
    if cpu is not None:
        changes["cpu"] = cpu
    if ram is not None:
        changes["ram"] = ram
    if disk is not None:
        changes["disk"] = disk
    if internet is not None:
        changes["internetMs"] = internet
    if broker_ping is not None:
        changes["brokerPingMs"] = broker_ping
    if t.get("uptimeSec") is not None:
        changes["uptimeSec"] = int(t["uptimeSec"])
    optional_fields = {
        "agentId": t.get("agentId"),
        "hostname": t.get("hostname"),
        "environment": t.get("environment"),
        "queueDepth": t.get("queueDepth"),
        "oldestPendingAgeSec": t.get("oldestPendingAgeSec"),
        "transportState": t.get("transportState"),
        "currentSessionId": t.get("currentSessionId") or t.get("sessionId"),
        "tradingProcessState": t.get("tradingProcessState"),
        "lastEodSync": t.get("lastEodSync"),
        "lastEodStatus": t.get("lastEodStatus"),
    }
    changes.update({key: value for key, value in optional_fields.items() if value is not None})
    changes = {key: value for key, value in changes.items() if value is not None}
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
                        env_id: str | None = None, mid: str | None = None,
                        session_id: str | None = None, sequence_id: int | None = None,
                        event_time: str | None = None) -> None:
    now = event_time or _now_iso()
    _touch_machine(mid, {"lastEvent": now})
    await _emit_event(
        data.get("category", "strategy"),
        data.get("severity", "info"),
        f"{machine} · {strategy}",
        data.get("message", ""),
        envelope_id=env_id, machine_id=mid, event_type=data.get("type") or "event",
        strategy=strategy, symbol=_symbol(data), session_id=session_id,
        sequence_id=sequence_id, payload_summary=_payload_summary(data),
        event_time=event_time,
    )


async def _handle_error(machine: str, strategy: str, data: dict[str, Any],
                        env_id: str | None = None, mid: str | None = None,
                        session_id: str | None = None, sequence_id: int | None = None,
                        event_time: str | None = None) -> None:
    now = event_time or _now_iso()
    _touch_machine(mid, {"lastEvent": now, "lastError": now})
    await _emit_event("system", "critical", f"{machine} · {strategy}",
                      f"Python exception: {data.get('message', '')}",
                      envelope_id=env_id, machine_id=mid, event_type="error",
                      strategy=strategy, symbol=_symbol(data), session_id=session_id,
                      sequence_id=sequence_id, payload_summary=_payload_summary(data),
                      event_time=event_time)
    _log("python", "error", strategy, data.get("message", ""), envelope_id=env_id, machine_id=mid)


async def _handle_trade(machine: str, strategy: str, data: dict[str, Any],
                        env_id: str | None = None, mid: str | None = None,
                        account: str | None = None, session_id: str | None = None,
                        sequence_id: int | None = None, event_time: str | None = None) -> None:
    action = data.get("action", "close")
    pnl = float(data.get("pnl", 0.0))
    direction = str(data.get("direction", "")).upper()
    severity = "warning" if action in ("rejected", "cancelled") else "info"
    now = event_time or _now_iso()
    _touch_machine(mid, {"lastEvent": now, "lastTrade": now})
    await _emit_event("trade", severity, f"{machine} · {strategy}",
                      f"Trade {action} {direction} {data.get('symbol', '')} · PnL {pnl:+.0f}",
                      envelope_id=env_id, machine_id=mid, event_type="trade",
                      strategy=strategy, symbol=_symbol(data), session_id=session_id,
                      sequence_id=sequence_id, payload_summary=_payload_summary(data),
                      event_time=event_time)
    _log("strategy", "info", strategy,
         f"trade() {data.get('symbol', '')} {action} pnl={pnl}", envelope_id=env_id, machine_id=mid)
    trade = _persist_trade(machine, strategy, data, env_id, mid, account, event_time=event_time)
    if trade is not None:
        await _broadcast_trade(trade)


def _persist_trade(machine: str, strategy: str, data: dict[str, Any],
                   env_id: str | None, mid: str | None, account: str | None,
                   event_time: str | None = None) -> dict | None:
    """Append a trade to the blotter (open/close/cancelled/rejected only)."""
    action = str(data.get("action", "close"))
    status = _TRADE_STATUS.get(action)
    if status is None:  # modify / pending are not blotter rows
        return None
    def _present(key: str, *alts: str) -> Any:
        for name in (key, *alts):
            if name in data and data[name] is not None:
                return data[name]
        return None

    trade = {
        "id": _next_id("trd"), "envelope_id": env_id, "time": event_time or _now_iso(),
        "strategy": strategy, "machine": machine, "machine_id": mid,
        "broker": data.get("broker") or "", "account": account or "",
        "symbol": data.get("symbol", ""), "direction": str(data.get("direction", "long")).lower(),
        "action": action, "entry": _present("entry"), "exit": _present("exit"),
        "quantity": _present("quantity"), "pnl": _present("pnl"),
        "latencyMs": _present("latencyMs", "latency_ms"),
        "durationSec": _present("durationSec", "duration_sec"),
        "status": status,
    }
    trades_repo.insert(trade)
    return trade


async def _handle_start(machine: str, strategy: str, data: dict[str, Any],
                        env_id: str | None = None, mid: str | None = None,
                        session_id: str | None = None, sequence_id: int | None = None,
                        event_time: str | None = None) -> None:
    now = event_time or _now_iso()
    _touch_machine(mid, {"lastEvent": now, "tradingProcessState": "running"})
    await _emit_event("strategy", "info", f"{machine} · {strategy}",
                      data.get("message", "Strategy started"), envelope_id=env_id, machine_id=mid,
                      event_type="strategy_started", strategy=strategy, symbol=_symbol(data),
                      session_id=session_id, sequence_id=sequence_id,
                      payload_summary=_payload_summary(data), event_time=event_time)
    _log("strategy", "info", strategy, f"start() on {machine}", envelope_id=env_id, machine_id=mid)


async def _handle_stop(machine: str, strategy: str, data: dict[str, Any],
                       env_id: str | None = None, mid: str | None = None,
                       session_id: str | None = None, sequence_id: int | None = None,
                       event_time: str | None = None) -> None:
    now = event_time or _now_iso()
    _touch_machine(mid, {"lastEvent": now, "tradingProcessState": "stopped"})
    await _emit_event("strategy", "warning", f"{machine} · {strategy}",
                      data.get("message", "Strategy stopped"), envelope_id=env_id, machine_id=mid,
                      event_type="strategy_stopped", strategy=strategy, symbol=_symbol(data),
                      session_id=session_id, sequence_id=sequence_id,
                      payload_summary=_payload_summary(data), event_time=event_time)
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


def _coerce_severity(value: Any, default: str = "info") -> str:
    severity = str(value or default).lower()
    return severity if severity in {"info", "warning", "critical"} else default


def _event_message(kind: str, data: dict[str, Any]) -> str:
    if data.get("message"):
        return str(data["message"])
    symbol = _symbol(data) or ""
    status = data.get("status") or data.get("state") or data.get("action") or ""
    if kind == "signal":
        return f"Signal {status} {symbol}".strip()
    if kind == "order":
        return f"Order {status} {data.get('side') or data.get('direction') or ''} {symbol}".strip()
    if kind == "fill":
        return f"Fill {data.get('quantity') or ''} {symbol} @ {data.get('price') or data.get('avgPrice') or ''}".strip()
    if kind == "pnl":
        value = data.get("pnl") or data.get("realizedPnl") or data.get("unrealizedPnl")
        return f"PnL update {symbol} {value}".strip()
    if kind == "risk":
        return f"Risk event {data.get('reason') or status}".strip()
    if kind == "sync_status":
        return f"Sync status {status}".strip()
    if kind == "recovery":
        return f"Recovery {status}".strip()
    return f"{kind.replace('_', ' ').title()} {status}".strip()


def _event_category(kind: str, data: dict[str, Any]) -> str:
    if kind in {"order", "fill", "pnl"}:
        return "trade"
    if kind in {"signal", "strategy_status"}:
        return "strategy"
    if kind == "risk":
        return "risk"
    if kind == "sync_status":
        return "data"
    if kind in {"system_status", "recovery"}:
        return "machine"
    return str(data.get("category") or "system")


async def _handle_phase3_operational(
    kind: str,
    machine: str,
    strategy: str,
    data: dict[str, Any],
    *,
    env_id: str | None = None,
    mid: str | None = None,
    session_id: str | None = None,
    sequence_id: int | None = None,
    event_time: str | None = None,
) -> None:
    """Persist/broadcast a Phase 3 observational telemetry event."""
    now = event_time or _now_iso()
    machine_changes: dict[str, Any] = {"lastEvent": now}
    if kind == "system_status":
        for payload_key, machine_key in (
            ("queueDepth", "queueDepth"),
            ("oldestPendingAgeSec", "oldestPendingAgeSec"),
            ("transportState", "transportState"),
            ("tradingProcessState", "tradingProcessState"),
            ("currentSessionId", "currentSessionId"),
        ):
            if data.get(payload_key) is not None:
                machine_changes[machine_key] = data[payload_key]
    elif kind == "sync_status":
        status = str(data.get("status") or data.get("state") or "").lower()
        machine_changes["lastEodStatus"] = status or None
        if status in {"ready", "complete", "completed", "success", "succeeded"}:
            machine_changes["lastEodSync"] = now
            machine_changes["lastSuccessfulUpload"] = now
    elif kind == "recovery":
        state = str(data.get("state") or data.get("status") or "recovering")
        machine_changes["transportState"] = state
        machine_changes["recoveryState"] = str(data.get("recoveryState") or state)
        machine_changes["lastRecovery"] = now
        if data.get("eventsRecovered") is not None:
            machine_changes["eventsRecovered"] = int(data["eventsRecovered"])
        if data.get("eodBacklog") is not None:
            machine_changes["eodBacklog"] = int(data["eodBacklog"])
    elif kind == "fill":
        machine_changes["lastTrade"] = now
    elif kind == "risk":
        machine_changes["lastError"] = now if _coerce_severity(data.get("severity"), "warning") == "critical" else None
    machine_changes = {key: value for key, value in machine_changes.items() if value is not None}
    _touch_machine(mid, machine_changes)

    await _emit_event(
        _event_category(kind, data),
        _coerce_severity(data.get("severity"), "warning" if kind == "risk" else "info"),
        f"{machine} · {strategy}",
        _event_message(kind, data),
        envelope_id=env_id,
        machine_id=mid,
        event_type=str(kind),
        strategy=strategy,
        symbol=_symbol(data),
        session_id=session_id,
        sequence_id=sequence_id,
        payload_summary=_payload_summary(data),
        event_time=event_time,
    )


async def _handle_system_health(
    machine: str,
    strategy: str,
    data: dict[str, Any],
    *,
    env_id: str | None = None,
    mid: str | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
    sequence_id: int | None = None,
    event_time: str | None = None,
) -> None:
    now = event_time or _now_iso()
    health_payload = data.get("health") if isinstance(data.get("health"), dict) else data

    tick_rate = float(health_payload.get("tick_rate", 0.0) or 0.0)
    tick_delay_ms = float(health_payload.get("tick_delay_ms", 0.0) or 0.0)
    queue_size = int(health_payload.get("queue_size", 0) or 0)
    queue_wait_ms = float(health_payload.get("queue_wait_ms", 0.0) or 0.0)
    avg_latency_ms = float(health_payload.get("avg_latency_ms", 0.0) or 0.0)
    p95_latency_ms = float(health_payload.get("p95_latency_ms", 0.0) or 0.0)
    p99_latency_ms = float(health_payload.get("p99_latency_ms", 0.0) or 0.0)
    api_success_pct = float(
        health_payload.get("api_success_pct", 100.0)
        if health_payload.get("api_success_pct") is not None
        else 100.0
    )
    signal_fill_rate_pct = float(health_payload.get("signal_fill_rate_pct", 0.0) or 0.0)
    cpu_usage_pct = float(health_payload.get("cpu_usage_pct", 0.0) or 0.0)
    memory_mb = float(health_payload.get("memory_mb", 0.0) or 0.0)
    status = str(health_payload.get("status", "STABLE") or "STABLE").upper()

    snapshot_id = _next_id("hlth")
    effective_mid = mid or machine_id_for(machine)
    system_health_repo.insert({
        "id": snapshot_id,
        "machine_id": effective_mid,
        "agent_id": agent_id,
        "event_id": env_id,
        "timestamp_utc": now,
        "tick_rate": tick_rate,
        "tick_delay_ms": tick_delay_ms,
        "queue_size": queue_size,
        "queue_wait_ms": queue_wait_ms,
        "avg_latency_ms": avg_latency_ms,
        "p95_latency_ms": p95_latency_ms,
        "p99_latency_ms": p99_latency_ms,
        "api_success_pct": api_success_pct,
        "signal_fill_rate_pct": signal_fill_rate_pct,
        "cpu_usage_pct": cpu_usage_pct,
        "memory_mb": memory_mb,
        "status": status,
    })

    machine_changes: dict[str, Any] = {
        "lastEvent": now,
        "cpu": cpu_usage_pct,
        "queueDepth": queue_size,
    }
    _touch_machine(effective_mid, machine_changes)

    summary = f"status={status}, cpu={cpu_usage_pct}%, lat_avg={avg_latency_ms}ms, p95={p95_latency_ms}ms, queue={queue_size}"
    await _emit_event(
        "machine",
        "info" if status == "STABLE" else "warning",
        f"{machine} · system_health",
        f"System Health {status}",
        envelope_id=env_id,
        machine_id=effective_mid,
        event_type="system_health",
        strategy=strategy,
        session_id=session_id,
        sequence_id=sequence_id,
        payload_summary=summary,
        event_time=event_time,
    )


# --------------------------------------------------------------------------- #
# Dispatch (single envelope, transactional + idempotent) + batch
# --------------------------------------------------------------------------- #
async def _dispatch_inner(env: Envelope, agent_id: str | None = None) -> None:
    kind = resolve_dispatch_kind(env) or env.kind
    machine, strategy, data = env.machine, env.strategy, env.data
    env_id = env.id
    mid = machine_id_for(machine) if machine and machine != "unknown" else None
    event_time = env.ts
    agent = agent_id or env.agent_id
    if kind in ("heartbeat", "metrics"):
        # Prefer the id in the payload, then the authenticated request header;
        # `_apply_machine_telemetry` falls back to the machine id if neither.
        await _handle_metrics(machine, {**data, "agentId": data.get("agentId") or agent, "ts": env.ts})
        if kind == "metrics":
            _persist_host_metrics(machine, mid, env_id, data)
    elif kind == "metric":
        _handle_metric(machine, strategy, data, env_id, mid)
    elif kind == "event":
        await _handle_event(machine, strategy, data, env_id, mid, env.session_id, env.sequence_id, event_time)
    elif kind == "error":
        await _handle_error(machine, strategy, data, env_id, mid, env.session_id, env.sequence_id, event_time)
    elif kind == "trade":
        await _handle_trade(machine, strategy, data, env_id, mid, env.account, env.session_id, env.sequence_id, event_time)
    elif kind == "position":
        _handle_position(machine, strategy, data, env_id, mid)
    elif kind == "start":
        await _handle_start(machine, strategy, data, env_id, mid, env.session_id, env.sequence_id, event_time)
    elif kind == "stop":
        await _handle_stop(machine, strategy, data, env_id, mid, env.session_id, env.sequence_id, event_time)
    elif kind == "log":
        _handle_log(machine, strategy, data, env_id, mid)
    elif kind == "system_health":
        await _handle_system_health(
            machine, strategy, data, env_id=env_id, mid=mid, agent_id=agent,
            session_id=env.session_id, sequence_id=env.sequence_id, event_time=event_time,
        )
    elif kind in {
        "system_status", "strategy_status", "signal", "order", "fill",
        "pnl", "risk", "sync_status", "recovery",
    }:
        await _handle_phase3_operational(
            kind, machine, strategy, data, env_id=env_id, mid=mid,
            session_id=env.session_id, sequence_id=env.sequence_id, event_time=event_time,
        )


def _dead_letter(env: Envelope, reason: str, error_type: str | None, agent_id: str | None) -> None:
    """Record a permanently unprocessable envelope. Never raises.

    A dead-letter write that fails must not turn a rejected envelope into a
    transient failure, or the agent would retry something that can never
    succeed. Worst case we lose the audit row and log the fact.
    """
    try:
        dead_letter_repo.insert({
            "envelope_id": env.id, "kind": env.kind, "machine": env.machine,
            "machine_id": machine_id_for(env.machine) if env.machine else None,
            "agent_id": agent_id, "strategy": env.strategy,
            "sequence_id": env.sequence_id, "reason": reason, "error_type": error_type,
            "payload_preview": repr(env.data),
        })
    except Exception:
        log.exception("dead-letter write failed envelope_id=%s kind=%s", env.id, env.kind)


async def _dispatch(env: Envelope, agent_id: str | None = None) -> tuple[Outcome, str | None]:
    """Process one envelope in a single transaction.

    Returns ``(outcome, reason)``. Never raises — the caller needs an outcome for
    every item so the acknowledgement can be truthful.
    """
    kind = resolve_dispatch_kind(env) or env.kind
    if kind not in KNOWN_KINDS:
        reason = f"unknown envelope kind '{kind}'"
        _dead_letter(env, reason, "UnknownKind", agent_id)
        return Outcome.REJECTED, reason

    try:
        with unit_of_work():
            if not reserve_envelope(env.id, kind):
                # Already processed. At-least-once delivery makes this normal,
                # not an error: no rows, no broadcast, no metric movement.
                return Outcome.DUPLICATE, None
            await _dispatch_inner(env, agent_id)
        return Outcome.ACCEPTED, None
    except SQLAlchemyError as exc:
        # Transient. The envelope stays in the agent's durable queue.
        log.warning("ingest transient failure envelope_id=%s kind=%s error=%s",
                    env.id, env.kind, type(exc).__name__)
        return Outcome.FAILED, f"database error: {type(exc).__name__}"
    except Exception as exc:
        # Permanent: a malformed payload fails identically on every redelivery.
        reason = _short_reason(f"{type(exc).__name__}: {exc}")
        log.warning("ingest rejected envelope_id=%s kind=%s error=%s",
                    env.id, env.kind, type(exc).__name__)
        _dead_letter(env, reason, type(exc).__name__, agent_id)
        return Outcome.REJECTED, reason


def _record_session(env: Envelope, mid: str | None) -> None:
    """Fold an envelope into its trading session, when it declares one."""
    if not env.session_id or not mid:
        return
    try:
        sessions_repo.touch(
            session_id=env.session_id, machine_id=mid, machine=env.machine,
            event_time=_parse_ts(env.ts), is_trade=(resolve_dispatch_kind(env) == "trade"),
        )
    except Exception:
        # Session bookkeeping is derived data; it must never fail an ingest that
        # has already persisted its primary rows.
        log.exception("session bookkeeping failed session_id=%s", env.session_id)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


async def handle_batch(batch: AgentBatch, agent_id: str | None = None) -> AgentAck:
    """Ingest a batch, reporting the true outcome of every envelope.

    Previously this swallowed per-item exceptions and acknowledged
    ``processed=len(items)`` regardless, so the agent deleted envelopes the
    server had actually dropped. Now every item gets a deterministic outcome,
    permanent failures are dead-lettered, and a transient failure surfaces to the
    caller (503) so the agent's durable queue retries instead of discarding.
    """
    counts = {o: 0 for o in Outcome}
    outcomes: list[EnvelopeOutcome] = []
    max_sequence: int | None = None
    latest_event_time: datetime | None = None
    session_id: str | None = None

    effective_agent_id = agent_id or batch.agentId
    mid = machine_id_for(batch.machine)

    for env in batch.items:
        outcome, reason = await _dispatch(env, effective_agent_id)
        counts[outcome] += 1
        if outcome is not Outcome.ACCEPTED:
            outcomes.append(EnvelopeOutcome(id=env.id, status=outcome.value, reason=reason))
        if outcome is Outcome.ACCEPTED:
            _record_session(env, mid)
        # Sequence/session bookkeeping tracks what the agent *sent*, including
        # duplicates: a redelivered envelope still proves that number arrived.
        if outcome in (Outcome.ACCEPTED, Outcome.DUPLICATE):
            if env.sequence_id is not None:
                max_sequence = env.sequence_id if max_sequence is None else max(max_sequence, env.sequence_id)
            ts = _parse_ts(env.ts)
            if ts is not None and (latest_event_time is None or ts > latest_event_time):
                latest_event_time = ts
            session_id = env.session_id or session_id

    state: dict[str, Any] = {}
    try:
        state = sync_state_repo.record_batch(
            machine_id=mid, machine=batch.machine, agent_id=effective_agent_id or "",
            max_sequence_id=max_sequence, last_event_time=latest_event_time,
            queue_depth=batch.queueDepth, accepted=counts[Outcome.ACCEPTED],
            duplicate=counts[Outcome.DUPLICATE], failed=counts[Outcome.FAILED],
            session_id=session_id,
        ) or {}
    except Exception:
        # Bookkeeping must not mask a successful ingest.
        log.exception("sync-state update failed machine_id=%s", mid)

    if counts[Outcome.ACCEPTED] > 0:
        upload_changes: dict[str, Any] = {
            "lastSuccessfulUpload": _now_iso(),
            "agentId": effective_agent_id,
        }
        if batch.queueDepth is not None:
            upload_changes["queueDepth"] = batch.queueDepth
        if session_id:
            upload_changes["currentSessionId"] = session_id
        _touch_machine(mid, upload_changes)

    log.info(
        "ingest batch machine_id=%s agent_id=%s total=%d accepted=%d duplicate=%d "
        "rejected=%d failed=%d gap=%s",
        mid, effective_agent_id, len(batch.items), counts[Outcome.ACCEPTED],
        counts[Outcome.DUPLICATE], counts[Outcome.REJECTED], counts[Outcome.FAILED],
        bool(state.get("lastGapAt")),
    )

    return AgentAck(
        accepted=counts[Outcome.FAILED] == 0,
        received=_now_iso(),
        kind="batch",
        # `processed` now means "genuinely persisted", not "received".
        processed=counts[Outcome.ACCEPTED],
        machineId=mid,
        total=len(batch.items),
        duplicate=counts[Outcome.DUPLICATE],
        rejected=counts[Outcome.REJECTED],
        failed=counts[Outcome.FAILED],
        outcomes=outcomes or None,
        lastSequenceId=state.get("lastSequenceId"),
        sequenceGap=bool(state.get("lastGapAt")) if state else None,
    )


# Thin wrappers for the per-kind direct endpoints — routed through the same
# transactional, idempotent dispatch path as the batch.
def _as_envelope(default_kind: str, env: Envelope) -> Envelope:
    """Copy an envelope for a per-kind endpoint without erasing a real type.

    ``POST /api/agent/trades`` used to force ``kind=trade``. A heartbeat or
    order posted to that path then became a closed blotter row. The path default
    is used only when the envelope has no classifiable type of its own.
    """
    resolved = resolve_dispatch_kind(env)
    kind = resolved or default_kind
    return Envelope(
        kind=kind,
        id=env.id,
        machine=env.machine,
        strategy=env.strategy,
        account=env.account,
        data=env.data,
        ts=env.ts,
        sequence_id=env.sequence_id,
        schema_version=env.schema_version,
        session_id=env.session_id,
        event_type=env.event_type,
        source_event_type=env.source_event_type,
        source=env.source,
        agent_id=env.agent_id,
    )


async def _handle_single(kind: str, env: Envelope, agent_id: str | None = None) -> AgentAck:
    """Run one envelope through the shared dispatch and report it honestly.

    Keeps the original five-field ack shape (the frontend and the existing
    contract test depend on it) while adding the same outcome breakdown the
    batch endpoint returns.
    """
    envelope = _as_envelope(kind, env)
    outcome, reason = await _dispatch(envelope, agent_id)
    mid = machine_id_for(env.machine) if env.machine else None
    if outcome is Outcome.ACCEPTED:
        _record_session(envelope, mid)
    ack_kind = resolve_dispatch_kind(envelope) or kind
    return AgentAck(
        accepted=outcome is not Outcome.FAILED,
        received=_now_iso(),
        kind=ack_kind,
        processed=1 if outcome is Outcome.ACCEPTED else 0,
        machineId=mid,
        total=1,
        duplicate=1 if outcome is Outcome.DUPLICATE else 0,
        rejected=1 if outcome is Outcome.REJECTED else 0,
        failed=1 if outcome is Outcome.FAILED else 0,
        outcomes=(
            None if outcome is Outcome.ACCEPTED
            else [EnvelopeOutcome(id=env.id, status=outcome.value, reason=reason)]
        ),
    )


async def handle_events(env: Envelope, agent_id: str | None = None) -> AgentAck:
    return await _handle_single("event", env, agent_id)


async def handle_metrics_endpoint(env: Envelope, agent_id: str | None = None) -> AgentAck:
    return await _handle_single("metrics", env, agent_id)


async def handle_trades_endpoint(env: Envelope, agent_id: str | None = None) -> AgentAck:
    return await _handle_single("trade", env, agent_id)


async def handle_logs_endpoint(env: Envelope, agent_id: str | None = None) -> AgentAck:
    return await _handle_single("log", env, agent_id)
