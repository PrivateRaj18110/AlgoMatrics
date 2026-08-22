"""Analytics schemas."""

from pydantic import BaseModel

from app.schemas.common import CategoryValue, TimeSeriesPoint


class HeatmapCell(BaseModel):
    row: str
    col: str
    value: float


class HeatmapSeries(BaseModel):
    rows: list[str]
    cols: list[str]
    cells: list[HeatmapCell]


class AnalyticsData(BaseModel):
    """Full analytics payload (series + heatmaps)."""

    dailyPnl: list[TimeSeriesPoint]
    weeklyPnl: list[TimeSeriesPoint]
    monthlyPnl: list[TimeSeriesPoint]
    winRateByStrategy: list[CategoryValue]
    profitFactorByStrategy: list[CategoryValue]
    latencyByMachine: list[CategoryValue]
    pnlHeatmap: HeatmapSeries
    machineLoadHeatmap: HeatmapSeries
