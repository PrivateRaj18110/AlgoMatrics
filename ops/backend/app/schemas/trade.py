"""Trade schemas."""

from typing import Literal

from pydantic import BaseModel

TradeDirection = Literal["long", "short"]
TradeStatus = Literal["open", "closed", "cancelled"]


class Trade(BaseModel):
    """A single executed trade."""

    id: str
    time: str
    strategy: str
    machine: str
    broker: str
    account: str
    symbol: str
    direction: TradeDirection
    entry: float | None = None
    exit: float | None
    quantity: float | None = None
    pnl: float | None = None
    latencyMs: float | None = None
    durationSec: int | None = None
    status: TradeStatus
