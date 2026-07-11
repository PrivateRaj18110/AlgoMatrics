"""Ingestion schemas — the contract the ``monitor_sdk`` posts against.

Every method on the future SDK maps to one model here:

    monitor.start()    -> StartPayload      POST /api/ingest/start
    monitor.heartbeat()-> HeartbeatPayload  POST /api/ingest/heartbeat
    monitor.trade()    -> TradePayload      POST /api/ingest/trade
    monitor.position() -> PositionPayload   POST /api/ingest/position
    monitor.metric()   -> MetricPayload     POST /api/ingest/metric
    monitor.event()    -> EventPayload      POST /api/ingest/event
    monitor.error()    -> ErrorPayload      POST /api/ingest/error
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class IngestBase(BaseModel):
    """Common identity envelope sent with every SDK call."""

    strategy: str = Field(..., description="Strategy code/name, e.g. 'MR-FX'.")
    machine: str = Field(..., description="Host identifier, e.g. 'London VPS'.")
    account: str | None = Field(None, description="Account label, e.g. 'LIVE-001'.")
    token: str | None = Field(None, description="Optional ingest auth token.")
    ts: str | None = Field(None, description="Client ISO timestamp (server fills if absent).")


class StartPayload(IngestBase):
    """`monitor.start()` — strategy boot announcement."""

    version: str | None = None
    broker: str | None = None
    symbols: list[str] = []


class HeartbeatPayload(IngestBase):
    """`monitor.heartbeat()` — periodic liveness + host telemetry."""

    cpu: float | None = None
    ram: float | None = None
    disk: float | None = None
    brokerPingMs: float | None = None
    openPositions: int | None = None


class TradePayload(IngestBase):
    """`monitor.trade()` — a closed/opened trade."""

    symbol: str
    direction: Literal["long", "short"]
    entry: float
    exit: float | None = None
    quantity: float
    pnl: float = 0.0
    latencyMs: float = 0.0
    durationSec: int = 0
    status: Literal["open", "closed", "cancelled"] = "closed"


class PositionPayload(IngestBase):
    """`monitor.position()` — open position snapshot."""

    symbol: str
    direction: Literal["long", "short"]
    quantity: float
    entry: float
    unrealizedPnl: float = 0.0


class MetricPayload(IngestBase):
    """`monitor.metric()` — an arbitrary named numeric metric."""

    name: str
    value: float
    unit: str | None = None


class EventPayload(IngestBase):
    """`monitor.event()` — a domain event for the terminal."""

    category: Literal["trade", "strategy", "machine", "broker", "system", "database", "risk"] = "strategy"
    severity: Literal["info", "warning", "critical"] = "info"
    message: str


class ErrorPayload(IngestBase):
    """`monitor.error()` — an exception / error report."""

    message: str
    traceback: str | None = None
    context: dict[str, Any] | None = None


class IngestAck(BaseModel):
    """Standard acknowledgement returned by every ingest endpoint."""

    accepted: bool = True
    received: str
    kind: str
