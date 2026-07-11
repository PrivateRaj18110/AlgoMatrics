"""Execution pipeline schemas."""

from typing import Literal

from pydantic import BaseModel

from app.schemas.common import TimeSeriesPoint

ExecutionStageKey = Literal[
    "signal", "risk", "created", "sent", "received", "filled", "open", "closed"
]
ExecutionResult = Literal["filled", "rejected", "partial"]


class ExecutionStage(BaseModel):
    key: ExecutionStageKey
    label: str
    avgMs: float
    count: int
    dropped: int
    status: Literal["ok", "warn", "fail"]


class LatencyBucket(BaseModel):
    label: str
    p50: float
    p90: float
    p95: float
    p99: float


class ExecutionFlowSample(BaseModel):
    id: str
    time: str
    symbol: str
    strategy: str
    signalMs: float
    riskMs: float
    execMs: float
    brokerMs: float
    fillMs: float
    totalMs: float
    result: ExecutionResult


class ExecutionData(BaseModel):
    stages: list[ExecutionStage]
    latency: list[LatencyBucket]
    recent: list[ExecutionFlowSample]
    throughput: list[TimeSeriesPoint]
