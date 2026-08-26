from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OpsModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class OpsOverview(OpsModel):
    machine_count: int | None = None
    online_machines: int | None = None
    closed_trade_count: int | None = None
    total_pnl: float | None = None
    awaiting_telemetry: bool = True
    telemetry_configured: bool = False


class OpsMachine(OpsModel):
    id: str
    name: str
    hostname: str | None = None
    agent_id: str | None = None
    status: str | None = None
    cpu: float | None = None
    ram: float | None = None
    disk: float | None = None
    temperature_c: float | None = None
    internet_ms: float | None = None
    broker_ping_ms: float | None = None
    uptime_sec: int | None = None
    last_heartbeat: str | None = None
    strategy_count: int | None = None
    last_successful_upload: str | None = None
    queue_depth: int | None = None
    oldest_pending_age_sec: int | None = None
    transport_state: str | None = None
    environment: str | None = None


class OpsEvent(OpsModel):
    id: str
    time: str | None = None
    received_at: str | None = None
    ingest_ts: str | None = None
    event_ts: str | None = None
    category: str | None = None
    severity: str | None = None
    source: str | None = None
    message: str | None = None
    machine_id: str | None = None
    event_type: str | None = None
    strategy: str | None = None
    symbol: str | None = None
    session_id: str | None = None
    sequence_id: int | None = None
    payload_summary: str | None = None
    level: str | None = None
    logger: str | None = None


class OpsTrade(OpsModel):
    id: str
    envelope_id: str | None = None
    time: str | None = None
    trade_ts: str | None = None
    strategy: str | None = None
    machine: str | None = None
    machine_id: str | None = None
    broker: str | None = None
    account: str | None = None
    symbol: str | None = None
    direction: str | None = None
    entry: float | None = None
    exit: float | None = None
    quantity: float | None = None
    pnl: float | None = None
    latency_ms: float | None = None
    duration_sec: float | None = None
    status: str | None = None


class OpsStrategyRow(OpsModel):
    strategy_id: str
    strategy_name: str | None = None
    machine_id: str | None = None
    status: str | None = None
    last_heartbeat: str | None = None
    symbols: list[str] = Field(default_factory=list)
    trade_count: int | None = None
    winning_trades: int | None = None
    losing_trades: int | None = None
    total_pnl: float | None = None
    gross_pnl: float | None = None
    average_trade: float | None = None
    best_trade: float | None = None
    worst_trade: float | None = None
    win_rate: float | None = None
    avg_latency_ms: float | None = None


class OpsSymbolRow(OpsModel):
    strategy_name: str | None = None
    symbol: str | None = None
    underlying: str | None = None
    instrument: str | None = None
    expiry: str | None = None
    strike: str | None = None
    option_type: str | None = None
    metadata_available: bool = False
    trade_count: int | None = None
    winning_trades: int | None = None
    losing_trades: int | None = None
    pnl: float | None = None
    average_trade: float | None = None
    best_trade: float | None = None
    worst_trade: float | None = None
    win_rate: float | None = None


class OpsAnalytics(OpsModel):
    strategies: list[OpsStrategyRow]
    symbols: list[OpsSymbolRow]
    by_symbol: list[OpsSymbolRow] = Field(default_factory=list)
    option_metadata: str
    timestamps: dict[str, Any]


class SystemHealthPoint(OpsModel):
    id: str | None = None
    machine_id: str
    agent_id: str | None = None
    event_id: str | None = None
    timestamp: str
    generated_at: str | None = None
    tick_rate: float = 0.0
    tick_delay_ms: float = 0.0
    queue_size: int = 0
    queue_wait_ms: float = 0.0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    api_success_pct: float = 100.0
    api_success_rate: float | None = None
    signal_fill_rate_pct: float = 0.0
    signal_fill_rate: float | None = None
    cpu_usage_pct: float = 0.0
    cpu_usage: float | None = None
    memory_mb: float = 0.0
    status: str = "STABLE"
    created_at: str | None = None
    received_at: str | None = None


class SystemHealthResponse(OpsModel):
    machine_id: str | None = None
    machine_name: str | None = None
    is_live: bool = False
    current_execution_status: str = "offline"
    current_health_status: str | None = None
    last_health_timestamp: str | None = None
    latest: SystemHealthPoint | None = None
    points: list[SystemHealthPoint] = Field(default_factory=list)
    snapshots: list[SystemHealthPoint] = Field(default_factory=list)
