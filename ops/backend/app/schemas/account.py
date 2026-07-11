"""Account schemas."""

from typing import Literal

from pydantic import BaseModel

from app.schemas.common import Status, TimeSeriesPoint

AccountType = Literal["live", "demo", "prop"]


class Account(BaseModel):
    """A trading account held at a broker."""

    id: str
    label: str
    broker: str
    type: AccountType
    currency: str
    status: Status
    balance: float
    equity: float
    todayPnl: float
    openPnl: float
    marginLevelPct: float
    leverage: int
    openPositions: int
    strategies: list[str]
    equityCurve: list[TimeSeriesPoint]
