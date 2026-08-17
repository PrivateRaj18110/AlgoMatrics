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
    spreadPips: float | None = None
    balance: float | None = None
    equity: float | None = None
    margin: float | None = None
    freeMargin: float | None = None
    marginLevelPct: float | None = None
    leverage: int | None = None
    openPositions: int | None = None
    pendingOrders: int | None = None
    rejectedOrders: int | None = None
    pingMs: float | None = None
    lastSync: str | None = None
    pingHistory: list[TimeSeriesPoint]
