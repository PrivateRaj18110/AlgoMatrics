"""Quant analytics and replay API schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class QuantCoverage(BaseModel):
    datasetId: str
    tradingDate: str
    machineId: str
    sessionId: str | None = None
    fileCount: int
    parsedFiles: int
    parsedRows: int
    skippedFiles: int
    datasetTypes: dict[str, int]


class QuantTradeMetrics(BaseModel):
    totalTrades: int
    closedTrades: int
    winningTrades: int
    losingTrades: int
    grossPnl: float
    averagePnl: float
    winRate: float
    profitFactor: float | None = None
    expectancy: float
    maxDrawdown: float
    sharpeLike: float | None = None
    symbols: dict[str, int] = Field(default_factory=dict)
    strategies: dict[str, int] = Field(default_factory=dict)


class ReplayPoint(BaseModel):
    t: str
    price: float
    equity: float | None = None


class QuantMarketReplay(BaseModel):
    available: bool
    symbol: str | None = None
    points: list[ReplayPoint] = Field(default_factory=list)
    startTime: str | None = None
    endTime: str | None = None
    startPrice: float | None = None
    endPrice: float | None = None
    returnPct: float | None = None
    high: float | None = None
    low: float | None = None
    maxDrawdownPct: float | None = None
    volatilityPct: float | None = None


AvailabilityStatus = Literal["AVAILABLE", "NOT_AVAILABLE", "INSUFFICIENT_DATA"]


class QuantAnalyticsMetric(BaseModel):
    status: AvailabilityStatus
    value: float | int | str | None = None
    unit: str | None = None
    reason: str | None = None
    requiredFields: list[str] = Field(default_factory=list)


class QuantAnalyticsSection(BaseModel):
    status: AvailabilityStatus
    calculationVersion: str
    lineage: dict[str, str | None] = Field(default_factory=dict)
    metrics: dict[str, QuantAnalyticsMetric] = Field(default_factory=dict)
    dimensions: dict[str, dict[str, int]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class QuantAnalyticsBundle(BaseModel):
    performance: QuantAnalyticsSection
    strategy: QuantAnalyticsSection
    execution: QuantAnalyticsSection
    signals: QuantAnalyticsSection
    risk: QuantAnalyticsSection
    sessions: QuantAnalyticsSection
    dataQuality: QuantAnalyticsSection


class QuantReportView(BaseModel):
    reportId: str
    datasetId: str
    machineId: str
    tradingDate: str
    status: Literal["READY", "PARTIAL", "EMPTY", "FAILED"]
    coverage: QuantCoverage
    tradeMetrics: QuantTradeMetrics
    marketReplay: QuantMarketReplay
    analytics: QuantAnalyticsBundle
    warnings: list[str] = Field(default_factory=list)
    createdAt: str
    updatedAt: str


class QuantAnalyticsReportItem(BaseModel):
    reportId: str
    datasetId: str
    machineId: str
    tradingDate: str
    status: Literal["READY", "PARTIAL", "EMPTY", "FAILED"]
    analytics: QuantAnalyticsSection


class QuantAnalyticsSummary(BaseModel):
    category: Literal[
        "performance",
        "strategy",
        "execution",
        "signals",
        "risk",
        "sessions",
        "dataQuality",
    ]
    generatedAt: str
    calculationVersion: str
    reportCount: int
    datasetId: str | None = None
    reports: list[QuantAnalyticsReportItem] = Field(default_factory=list)


class SyntheticReplayRequest(BaseModel):
    seed: int = 42
    symbol: str = "SYNTH"
    steps: int = Field(default=250, ge=2, le=10_000)
    startPrice: float = Field(default=100.0, gt=0)
    driftBps: float = 0.0
    volatilityBps: float = Field(default=50.0, ge=0.0)


class SyntheticReplayResult(BaseModel):
    seed: int
    symbol: str
    steps: int
    replay: QuantMarketReplay
    tradeMetrics: QuantTradeMetrics
