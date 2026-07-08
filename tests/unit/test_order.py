from decimal import Decimal
from uuid import uuid4

import pytest

from algo_platform.modules.trading.domain.orders import (
    Order,
    OrderIntent,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from algo_platform.shared.domain.errors import InvariantViolation
from algo_platform.shared.domain.types import AccountId, Side, StrategyRunId, TenantId


def make_intent(**overrides: object) -> OrderIntent:
    defaults: dict[str, object] = {
        "tenant_id": TenantId(uuid4()),
        "account_id": AccountId(uuid4()),
        "strategy_run_id": StrategyRunId(uuid4()),
        "instrument_id": uuid4(),
        "side": Side.BUY,
        "quantity": Decimal("10"),
        "order_type": OrderType.MARKET,
        "time_in_force": TimeInForce.DAY,
        "client_order_id": "test-1",
    }
    defaults.update(overrides)
    return OrderIntent(**defaults)  # type: ignore[arg-type]


def test_order_intent_rejects_non_positive_quantity() -> None:
    with pytest.raises(ValueError, match="quantity must be positive"):
        make_intent(quantity=Decimal("0"))


def test_order_intent_requires_limit_price_for_limit_orders() -> None:
    with pytest.raises(ValueError, match="limit price required"):
        make_intent(order_type=OrderType.LIMIT)


def test_order_intent_requires_stop_price_for_stop_orders() -> None:
    with pytest.raises(ValueError, match="stop price required"):
        make_intent(order_type=OrderType.STOP)


def test_full_lifecycle_market_order() -> None:
    order = Order.place(make_intent())
    assert order.status is OrderStatus.PENDING_RISK

    order.approve()
    assert order.status is OrderStatus.APPROVED

    order.mark_submitted("brk-1")
    assert order.status is OrderStatus.SUBMITTED
    assert order.broker_order_id == "brk-1"

    order.apply_fill(Decimal("4"), Decimal("100"))
    assert order.status is OrderStatus.PARTIALLY_FILLED
    assert order.filled_quantity == Decimal("4")
    assert order.average_fill_price == Decimal("100")

    order.apply_fill(Decimal("6"), Decimal("110"))
    assert order.status is OrderStatus.FILLED
    assert order.filled_quantity == Decimal("10")
    assert order.average_fill_price == Decimal("106")
    assert order.remaining_quantity == Decimal("0")

    event_types = [e.event_type for e in order.events]
    assert "trading.order_placed.v1" in event_types
    assert "trading.order_filled.v1" in event_types


def test_fill_cannot_exceed_remaining() -> None:
    order = Order.place(make_intent())
    order.approve()
    order.mark_submitted("brk-2")
    with pytest.raises(InvariantViolation, match="exceeds remaining"):
        order.apply_fill(Decimal("11"), Decimal("100"))


def test_cannot_approve_twice() -> None:
    order = Order.place(make_intent())
    order.approve()
    with pytest.raises(InvariantViolation):
        order.approve()


def test_cancel_flow() -> None:
    order = Order.place(make_intent())
    order.approve()
    order.mark_submitted("brk-3")
    order.request_cancel()
    assert order.status is OrderStatus.CANCEL_PENDING
    order.confirm_cancelled()
    assert order.status is OrderStatus.CANCELLED
    assert not order.is_open


def test_reject_terminal_is_final() -> None:
    order = Order.place(make_intent())
    order.reject("risk: max_order_value_exceeded")
    assert order.status is OrderStatus.REJECTED
    with pytest.raises(InvariantViolation):
        order.reject("again")
    with pytest.raises(InvariantViolation):
        order.request_cancel()


def test_fill_on_cancel_pending_still_applies() -> None:
    order = Order.place(make_intent())
    order.approve()
    order.mark_submitted("brk-4")
    order.request_cancel()
    order.apply_fill(Decimal("10"), Decimal("99"))
    assert order.status is OrderStatus.FILLED
