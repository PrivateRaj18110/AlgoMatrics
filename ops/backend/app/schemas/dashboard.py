"""Dashboard overview schemas."""

from typing import Literal

from pydantic import BaseModel

from app.schemas.common import TimeSeriesPoint, Trend

KpiFormat = Literal["currency", "percent", "number", "ratio"]


class KpiMetric(BaseModel):
    """A headline KPI rendered as a metric card."""

    id: str
    label: str
    value: float
    format: KpiFormat
    deltaPct: float | None = None
    trend: Trend | None = None
    higherIsBetter: bool | None = None


class DashboardOverview(BaseModel):
    """Aggregated dashboard payload."""

    kpis: list[KpiMetric]
    equityCurve: list[TimeSeriesPoint]
    dailyPnl: list[TimeSeriesPoint]
    performance: list[TimeSeriesPoint]
