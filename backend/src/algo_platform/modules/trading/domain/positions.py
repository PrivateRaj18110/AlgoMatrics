"""Net-position projection with realized/unrealized PnL arithmetic."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from algo_platform.shared.domain.errors import InvariantViolation
from algo_platform.shared.domain.types import AccountId, Side, TenantId, utc_now


@dataclass(frozen=True, slots=True)
class Execution:
    """Immutable fill fact. One order may produce many executions."""

    id: UUID
    order_id: UUID
    organization_id: TenantId
    account_id: AccountId
    instrument_id: UUID
    side: Side
    quantity: Decimal
    price: Decimal
    fee: Decimal
    fee_currency: str
    executed_at: datetime
    broker_execution_id: str

    @classmethod
    def record(
        cls,
        *,
        order_id: UUID,
        organization_id: TenantId,
        account_id: AccountId,
        instrument_id: UUID,
        side: Side,
        quantity: Decimal,
        price: Decimal,
        fee: Decimal,
        fee_currency: str,
        broker_execution_id: str,
        executed_at: datetime | None = None,
    ) -> Execution:
        if quantity <= 0 or price <= 0:
            raise InvariantViolation("execution quantity and price must be positive")
        if fee < 0:
            raise InvariantViolation("execution fee cannot be negative")
        return cls(
            id=uuid4(),
            order_id=order_id,
            organization_id=organization_id,
            account_id=account_id,
            instrument_id=instrument_id,
            side=side,
            quantity=quantity,
            price=price,
            fee=fee,
            fee_currency=fee_currency,
            executed_at=executed_at or utc_now(),
            broker_execution_id=broker_execution_id,
        )


@dataclass(slots=True)
class Position:
    """Signed net position: positive quantity = long, negative = short."""

    id: UUID
    organization_id: TenantId
    account_id: AccountId
    instrument_id: UUID
    quantity: Decimal = Decimal("0")
    average_price: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    fees_paid: Decimal = Decimal("0")
    last_mark: Decimal | None = None
    opened_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    version: int = 1

    @classmethod
    def open_empty(
        cls,
        *,
        organization_id: TenantId,
        account_id: AccountId,
        instrument_id: UUID,
    ) -> Position:
        return cls(
            id=uuid4(),
            organization_id=organization_id,
            account_id=account_id,
            instrument_id=instrument_id,
        )

    @property
    def is_flat(self) -> bool:
        return self.quantity == 0

    @property
    def side(self) -> str:
        if self.quantity > 0:
            return "long"
        if self.quantity < 0:
            return "short"
        return "flat"

    @property
    def unrealized_pnl(self) -> Decimal:
        if self.last_mark is None or self.quantity == 0:
            return Decimal("0")
        return (self.last_mark - self.average_price) * self.quantity

    @property
    def market_value(self) -> Decimal:
        if self.last_mark is None:
            return abs(self.quantity) * self.average_price
        return abs(self.quantity) * self.last_mark

    def apply_execution(
        self, side: Side, quantity: Decimal, price: Decimal, fee: Decimal
    ) -> Decimal:
        """Apply a fill; returns the realized PnL delta produced by this fill."""
        if quantity <= 0:
            raise InvariantViolation("execution quantity must be positive")
        signed = quantity if side is Side.BUY else -quantity
        realized_delta = Decimal("0")

        if self.quantity == 0 or (self.quantity > 0) == (signed > 0):
            # Extending in the same direction: recompute weighted average.
            total = abs(self.quantity) + quantity
            self.average_price = (
                (self.average_price * abs(self.quantity)) + (price * quantity)
            ) / total
            self.quantity += signed
        else:
            closing = min(abs(self.quantity), quantity)
            direction = Decimal("1") if self.quantity > 0 else Decimal("-1")
            realized_delta = (price - self.average_price) * closing * direction
            self.realized_pnl += realized_delta
            remaining = quantity - closing
            self.quantity += signed
            if remaining > 0:
                # Crossed through zero: remainder opens the opposite side.
                self.average_price = price
            elif self.quantity == 0:
                self.average_price = Decimal("0")

        self.fees_paid += fee
        self.realized_pnl -= fee
        realized_delta -= fee
        self.updated_at = utc_now()
        self.version += 1
        return realized_delta

    def mark(self, price: Decimal) -> None:
        if price <= 0:
            raise InvariantViolation("mark price must be positive")
        self.last_mark = price
        self.updated_at = utc_now()
