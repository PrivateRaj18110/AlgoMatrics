from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from algo_platform.modules.trading.domain.orders import OrderIntent, OrderStatus


@dataclass(frozen=True, slots=True)
class BrokerOrderAck:
    broker_order_id: str
    client_order_id: str
    status: OrderStatus
    accepted_at: datetime


@dataclass(frozen=True, slots=True)
class BrokerOrderUpdate:
    broker_order_id: str
    client_order_id: str
    status: OrderStatus
    filled_quantity: Decimal
    average_price: Decimal | None
    occurred_at: datetime
    raw_reference: str | None = None


class BrokerExecutionPort(Protocol):
    """Command-side interface implemented by every broker adapter."""

    async def connect(self) -> None: ...

    async def disconnect(self) -> None: ...

    async def health(self) -> bool: ...

    async def submit_order(self, intent: OrderIntent) -> BrokerOrderAck: ...

    async def cancel_order(self, broker_order_id: str) -> BrokerOrderAck: ...

    async def replace_order(
        self,
        broker_order_id: str,
        *,
        quantity: Decimal | None = None,
        limit_price: Decimal | None = None,
        stop_price: Decimal | None = None,
    ) -> BrokerOrderAck: ...

    def stream_order_updates(self) -> AsyncIterator[BrokerOrderUpdate]:
        """Async generator of normalized updates (implementations use ``yield``)."""
        ...


class BrokerAccountPort(Protocol):
    """Query/reconciliation interface; implementations normalize venue semantics."""

    async def get_balances(self) -> dict[str, Decimal]: ...

    async def get_open_orders(self) -> list[BrokerOrderUpdate]: ...

    async def get_positions(self) -> list[dict[str, object]]: ...
