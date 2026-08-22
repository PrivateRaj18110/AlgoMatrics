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
    balance: float | None = None
    equity: float | None = None
    todayPnl: float | None = None
    openPnl: float | None = None
    marginLevelPct: float | None = None
    leverage: int | None = None
    openPositions: int | None = None
    strategies: list[str]
    equityCurve: list[TimeSeriesPoint]
