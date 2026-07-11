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
    todayPnl: float
    weekPnl: float
    todayTrades: int
    openPositions: int
    winRate: float
    profitFactor: float
    avgLatencyMs: float
    sparkline: list[TimeSeriesPoint]
    lastHeartbeat: str
