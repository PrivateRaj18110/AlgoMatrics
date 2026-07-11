"""Ingestion service — the server side of the ``monitor_sdk`` contract.

Each SDK call is normalised into the platform's domain records: trades land in
the blotter feed, events stream to the terminal, errors become critical events
and log lines, metrics/positions/heartbeats are accepted and (later) persisted.
Everything is also broadcast to websocket clients so dashboards update live.

The flow is intentionally storage-agnostic: today it appends to in-memory
repositories; with Supabase wired up these become INSERTs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.repositories import events_repo, logs_repo
from app.realtime.broadcaster import broadcaster
from app.schemas.ingest import (
    ErrorPayload,
    EventPayload,
    HeartbeatPayload,
    IngestAck,
    MetricPayload,
    PositionPayload,
    StartPayload,
    TradePayload,
)

def _next_id(prefix: str) -> str:
    return f"{prefix}-ingest-{uuid4().hex}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ack(kind: str) -> IngestAck:
    return IngestAck(accepted=True, received=_now_iso(), kind=kind)


async def _emit_event(category: str, severity: str, source: str, message: str) -> dict:
    event = {
        "id": _next_id("evt"), "time": _now_iso(), "category": category,
        "severity": severity, "source": source, "message": message,
    }
    events_repo.prepend(event)
    await broadcaster.broadcast({"type": "event", "payload": event})
    return event


def _log(source: str, level: str, logger: str, message: str) -> None:
    logs_repo.prepend({
        "id": _next_id("log"), "time": _now_iso(),
        "source": source, "level": level, "logger": logger, "message": message,
    })


async def handle_start(p: StartPayload) -> IngestAck:
    await _emit_event("strategy", "info", f"{p.machine} · {p.strategy}",
                      f"Strategy started{f' v{p.version}' if p.version else ''}")
    _log("strategy", "info", p.strategy, f"start() on {p.machine}")
    return _ack("start")


async def handle_heartbeat(p: HeartbeatPayload) -> IngestAck:
    _log("python", "debug", "monitor_sdk", f"heartbeat() from {p.strategy}@{p.machine}")
    return _ack("heartbeat")


async def handle_trade(p: TradePayload) -> IngestAck:
    verb = "opened" if p.status == "open" else "closed"
    await _emit_event("trade", "info", f"{p.machine} · {p.strategy}",
                      f"Trade {verb} {p.direction.upper()} {p.symbol} · PnL {p.pnl:+.0f}")
    _log("strategy", "info", p.strategy, f"trade() {p.symbol} {p.status} pnl={p.pnl}")
    return _ack("trade")


async def handle_position(p: PositionPayload) -> IngestAck:
    _log("strategy", "info", p.strategy,
         f"position() {p.direction} {p.symbol} qty={p.quantity} uPnL={p.unrealizedPnl}")
    return _ack("position")


async def handle_metric(p: MetricPayload) -> IngestAck:
    _log("strategy", "debug", p.strategy, f"metric() {p.name}={p.value}{p.unit or ''}")
    return _ack("metric")


async def handle_event(p: EventPayload) -> IngestAck:
    await _emit_event(p.category, p.severity, f"{p.machine} · {p.strategy}", p.message)
    return _ack("event")


async def handle_error(p: ErrorPayload) -> IngestAck:
    await _emit_event("system", "critical", f"{p.machine} · {p.strategy}",
                      f"Python exception: {p.message}")
    _log("python", "error", p.strategy, p.message)
    return _ack("error")
