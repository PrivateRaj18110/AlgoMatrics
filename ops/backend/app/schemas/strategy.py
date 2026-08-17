"""Strategy schemas."""

from pydantic import BaseModel

from app.schemas.common import Status, TimeSeriesPoint


class Strategy(BaseModel):
    """A trading strategy / algo instance running on a machine."""

    id: str
    name: str
    code: str
    description: str
    status: Status
    machineId: str
    machineName: str
    broker: str
    symbols: list[str]
    todayPnl: float | None = None
    weekPnl: float | None = None
    todayTrades: int | None = None
    openPositions: int | None = None
    winRate: float | None = None
    profitFactor: float | None = None
    avgLatencyMs: float | None = None
    sparkline: list[TimeSeriesPoint]
    lastHeartbeat: str | None = None
