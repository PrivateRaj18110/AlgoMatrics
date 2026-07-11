"""Broker schemas."""

from pydantic import BaseModel

from app.schemas.common import Status, TimeSeriesPoint


class Broker(BaseModel):
    """A connected broker / liquidity venue."""

    id: str
    name: str
    server: str
    connection: Status
    account: str
    spreadPips: float
    balance: float
    equity: float
    margin: float
    freeMargin: float
    marginLevelPct: float
    leverage: int
    openPositions: int
    pendingOrders: int
    rejectedOrders: int
    pingMs: float
    lastSync: str
    pingHistory: list[TimeSeriesPoint]
