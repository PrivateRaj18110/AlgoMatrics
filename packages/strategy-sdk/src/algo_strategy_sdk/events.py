from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Tick:
    instrument: str
    timestamp: datetime
    bid: Decimal
    ask: Decimal
    last: Decimal | None = None


@dataclass(frozen=True, slots=True)
class Candle:
    instrument: str
    timeframe: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True, slots=True)
class Signal:
    name: str
    instrument: str
    strength: Decimal
    attributes: Mapping[str, str | int | float | bool]


@dataclass(frozen=True, slots=True)
class OrderUpdate:
    client_order_id: str
    status: str
    filled_quantity: Decimal
    average_price: Decimal | None


@dataclass(frozen=True, slots=True)
class PositionUpdate:
    instrument: str
    quantity: Decimal
    average_price: Decimal
    unrealized_pnl: Decimal
