"""Broker plugin protocol and a deterministic in-memory simulator plugin.

The agent never accepts shell commands or strategy source. A plugin implements
the narrow broker surface the platform needs; the MT5 plugin (see ``mt5.py``)
binds this to the MetaTrader5 terminal on a Windows host. The simulator plugin
lets the agent run and be tested without a terminal.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class OrderRequest:
    client_order_id: str
    symbol: str
    side: str
    order_type: str
    volume: Decimal
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None


@dataclass(slots=True)
class AgentOrder:
    order_id: str
    client_order_id: str
    symbol: str
    side: str
    volume: Decimal
    status: str
    filled_volume: Decimal = Decimal("0")
    average_price: Decimal | None = None


class BrokerPlugin(Protocol):
    def health(self) -> dict[str, object]: ...

    def submit(self, request: OrderRequest) -> AgentOrder: ...

    def cancel(self, order_id: str) -> AgentOrder: ...

    def replace(
        self,
        order_id: str,
        *,
        volume: Decimal | None,
        limit_price: Decimal | None,
        stop_price: Decimal | None,
    ) -> AgentOrder: ...

    def orders(self) -> list[AgentOrder]: ...

    def account(self) -> dict[str, object]: ...

    def positions(self) -> list[dict[str, object]]: ...


class SimulatorPlugin:
    """Thread-safe in-memory venue: market orders fill instantly at a mark price.

    Deterministic and dependency-free so the agent is runnable and testable
    without a broker terminal. Not for production trading.
    """

    def __init__(
        self,
        *,
        account_id: str = "SIM-0001",
        currency: str = "USD",
        starting_balance: Decimal = Decimal("100000"),
        mark_price: Decimal = Decimal("100"),
    ) -> None:
        self._account_id = account_id
        self._currency = currency
        self._balance = starting_balance
        self._mark = mark_price
        self._orders: dict[str, AgentOrder] = {}
        self._positions: dict[str, Decimal] = {}
        self._lock = threading.Lock()

    def health(self) -> dict[str, object]:
        return {
            "terminal_connected": True,
            "account": self._account_id,
            "currency": self._currency,
            "plugin": "simulator",
            "checked_at": datetime.now(UTC).isoformat(),
        }

    def submit(self, request: OrderRequest) -> AgentOrder:
        with self._lock:
            order = AgentOrder(
                order_id=f"sim-{uuid4().hex[:12]}",
                client_order_id=request.client_order_id,
                symbol=request.symbol,
                side=request.side,
                volume=request.volume,
                status="submitted",
            )
            if request.order_type == "market":
                price = request.limit_price or self._mark
                order.filled_volume = request.volume
                order.average_price = price
                order.status = "filled"
                signed = request.volume if request.side == "buy" else -request.volume
                self._positions[request.symbol] = (
                    self._positions.get(request.symbol, Decimal("0")) + signed
                )
                self._balance -= signed * price
            self._orders[order.order_id] = order
            return order

    def cancel(self, order_id: str) -> AgentOrder:
        with self._lock:
            order = self._orders.get(order_id)
            if order is None:
                raise KeyError(order_id)
            if order.status in {"submitted"}:
                order.status = "cancelled"
            return order

    def replace(
        self,
        order_id: str,
        *,
        volume: Decimal | None,
        limit_price: Decimal | None,
        stop_price: Decimal | None,
    ) -> AgentOrder:
        with self._lock:
            order = self._orders.get(order_id)
            if order is None:
                raise KeyError(order_id)
            if volume is not None and order.status == "submitted":
                order.volume = volume
            _ = (limit_price, stop_price)
            return order

    def orders(self) -> list[AgentOrder]:
        with self._lock:
            return list(self._orders.values())

    def account(self) -> dict[str, object]:
        with self._lock:
            return {
                "account": self._account_id,
                "currency": self._currency,
                "balance": str(self._balance),
            }

    def positions(self) -> list[dict[str, object]]:
        with self._lock:
            return [
                {"symbol": symbol, "volume": str(volume)}
                for symbol, volume in self._positions.items()
                if volume != 0
            ]


def order_payload(order: AgentOrder) -> dict[str, object]:
    return {
        "order_id": order.order_id,
        "client_order_id": order.client_order_id,
        "symbol": order.symbol,
        "side": order.side,
        "status": order.status,
        "filled_volume": str(order.filled_volume),
        "average_price": str(order.average_price) if order.average_price is not None else None,
    }
