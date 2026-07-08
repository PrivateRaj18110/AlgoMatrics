"""Shared utilities for NSE broker adapters (Zerodha, Angel One)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from algo_platform.modules.trading.domain.orders import OrderType, TimeInForce
from algo_platform.shared.domain.errors import ValidationFailed


@dataclass(frozen=True, slots=True)
class VenueInstrument:
    """Venue-facing identification the engine resolves before routing."""

    symbol: str
    exchange: str
    lot_size: Decimal
    token: str = ""


def to_nse_transaction_type(side: str) -> str:
    return "BUY" if side == "buy" else "SELL"


def to_nse_order_type(order_type: OrderType) -> str:
    mapping = {
        OrderType.MARKET: "MARKET",
        OrderType.LIMIT: "LIMIT",
        OrderType.STOP: "SL-M",
        OrderType.STOP_LIMIT: "SL",
    }
    return mapping[order_type]


def to_nse_validity(tif: TimeInForce) -> str:
    if tif is TimeInForce.DAY:
        return "DAY"
    if tif is TimeInForce.IOC:
        return "IOC"
    raise ValidationFailed(f"NSE venues do not support time-in-force '{tif.value}'")


def ensure_lot_multiple(quantity: Decimal, lot_size: Decimal, symbol: str) -> int:
    if lot_size <= 0:
        lot_size = Decimal("1")
    if quantity % lot_size != 0:
        raise ValidationFailed(
            f"quantity for {symbol} must be a multiple of the lot size {lot_size}"
        )
    return int(quantity)


NSE_ORDER_STATUS_MAP = {
    "OPEN": "submitted",
    "TRIGGER PENDING": "submitted",
    "PENDING": "submitted",
    "PUT ORDER REQ RECEIVED": "submitted",
    "VALIDATION PENDING": "submitted",
    "OPEN PENDING": "submitted",
    "MODIFY PENDING": "submitted",
    "COMPLETE": "filled",
    "CANCELLED": "cancelled",
    "REJECTED": "rejected",
}
