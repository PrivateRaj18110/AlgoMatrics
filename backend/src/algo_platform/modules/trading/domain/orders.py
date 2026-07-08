from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from algo_platform.shared.domain.errors import InvariantViolation
from algo_platform.shared.domain.types import (
    AccountId,
    DomainEvent,
    OrderId,
    Side,
    StrategyRunId,
    TenantId,
    utc_now,
)


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class TimeInForce(StrEnum):
    DAY = "day"
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"


class OrderStatus(StrEnum):
    PENDING_RISK = "pending_risk"
    APPROVED = "approved"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCEL_PENDING = "cancel_pending"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


OPEN_STATUSES = frozenset(
    {
        OrderStatus.PENDING_RISK,
        OrderStatus.APPROVED,
        OrderStatus.SUBMITTED,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.CANCEL_PENDING,
    }
)

TERMINAL_STATUSES = frozenset({OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED})


@dataclass(frozen=True, slots=True)
class OrderIntent:
    tenant_id: TenantId
    account_id: AccountId
    strategy_run_id: StrategyRunId | None
    instrument_id: UUID
    side: Side
    quantity: Decimal
    order_type: OrderType
    time_in_force: TimeInForce
    client_order_id: str
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")
        if self.order_type in {OrderType.LIMIT, OrderType.STOP_LIMIT} and self.limit_price is None:
            raise ValueError("limit price required")
        if self.order_type in {OrderType.STOP, OrderType.STOP_LIMIT} and self.stop_price is None:
            raise ValueError("stop price required")
        if self.limit_price is not None and self.limit_price <= 0:
            raise ValueError("limit price must be positive")
        if self.stop_price is not None and self.stop_price <= 0:
            raise ValueError("stop price must be positive")
        if not self.client_order_id or len(self.client_order_id) > 64:
            raise ValueError("client order id must be 1-64 characters")


@dataclass(slots=True)
class Order:
    id: OrderId
    intent: OrderIntent
    status: OrderStatus
    filled_quantity: Decimal = Decimal("0")
    average_fill_price: Decimal | None = None
    broker_order_id: str | None = None
    rejection_reason: str | None = None
    source: str = "manual"
    version: int = 1
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    events: list[DomainEvent] = field(default_factory=list, repr=False)

    @classmethod
    def place(cls, intent: OrderIntent, *, source: str = "manual") -> Order:
        order = cls(id=OrderId(uuid4()), intent=intent, status=OrderStatus.PENDING_RISK)
        order.source = source
        order._record("trading.order_placed.v1")
        return order

    @property
    def remaining_quantity(self) -> Decimal:
        return self.intent.quantity - self.filled_quantity

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_STATUSES

    def approve(self) -> None:
        self._require_status(OrderStatus.PENDING_RISK, action="approve")
        self.status = OrderStatus.APPROVED
        self._bump()
        self._record("trading.order_approved.v1")

    def reject(self, reason: str) -> None:
        if self.status in TERMINAL_STATUSES:
            raise InvariantViolation(f"cannot reject order in {self.status}")
        self.status = OrderStatus.REJECTED
        self.rejection_reason = reason[:300]
        self._bump()
        self._record("trading.order_rejected.v1")

    def mark_submitted(self, broker_order_id: str) -> None:
        if self.status not in {OrderStatus.APPROVED, OrderStatus.PENDING_RISK}:
            raise InvariantViolation(f"cannot submit order in {self.status}")
        self.status = OrderStatus.SUBMITTED
        self.broker_order_id = broker_order_id
        self._bump()
        self._record("trading.order_submitted.v1")

    def apply_fill(self, quantity: Decimal, price: Decimal) -> None:
        if quantity <= 0 or price <= 0:
            raise InvariantViolation("fill quantity and price must be positive")
        if self.status not in {
            OrderStatus.SUBMITTED,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.CANCEL_PENDING,
        }:
            raise InvariantViolation(f"cannot fill order in {self.status}")
        if quantity > self.remaining_quantity:
            raise InvariantViolation("fill exceeds remaining quantity")
        prior_notional = (self.average_fill_price or Decimal("0")) * self.filled_quantity
        self.filled_quantity += quantity
        self.average_fill_price = (prior_notional + price * quantity) / self.filled_quantity
        self.status = (
            OrderStatus.FILLED if self.remaining_quantity == 0 else OrderStatus.PARTIALLY_FILLED
        )
        self._bump()
        self._record(
            "trading.order_filled.v1"
            if self.status is OrderStatus.FILLED
            else "trading.order_partially_filled.v1"
        )

    def request_cancel(self) -> None:
        if self.status not in {
            OrderStatus.APPROVED,
            OrderStatus.SUBMITTED,
            OrderStatus.PARTIALLY_FILLED,
        }:
            raise InvariantViolation(f"cannot cancel order in {self.status}")
        self.status = OrderStatus.CANCEL_PENDING
        self._bump()
        self._record("trading.order_cancel_requested.v1")

    def confirm_cancelled(self) -> None:
        if self.status not in {
            OrderStatus.CANCEL_PENDING,
            OrderStatus.SUBMITTED,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.APPROVED,
        }:
            raise InvariantViolation(f"cannot confirm cancel in {self.status}")
        self.status = OrderStatus.CANCELLED
        self._bump()
        self._record("trading.order_cancelled.v1")

    def _require_status(self, expected: OrderStatus, *, action: str) -> None:
        if self.status is not expected:
            raise InvariantViolation(f"cannot {action} order in {self.status}")

    def _bump(self) -> None:
        self.version += 1
        self.updated_at = utc_now()

    def _record(self, event_type: str) -> None:
        self.events.append(
            DomainEvent.new(
                event_type=event_type,
                aggregate_id=self.id,
                tenant_id=self.intent.tenant_id,
            )
        )
