from decimal import Decimal
from uuid import uuid4

from algo_platform.modules.trading.domain.orders import OrderType
from algo_platform.modules.trading.infrastructure.brokers.paper import (
    PaperExecutionSimulator,
    PaperMarketState,
)
from algo_platform.shared.domain.types import Side

MARKET = PaperMarketState(bid=Decimal("99.95"), ask=Decimal("100.05"))


def test_market_fill_is_deterministic_per_order() -> None:
    simulator = PaperExecutionSimulator(seed=42)
    order_id = uuid4()
    first = simulator.fill_market_order(
        order_id=order_id, side=Side.BUY, remaining_quantity=Decimal("100"), market=MARKET
    )
    second = simulator.fill_market_order(
        order_id=order_id, side=Side.BUY, remaining_quantity=Decimal("100"), market=MARKET
    )
    assert first == second


def test_market_buy_pays_at_or_above_ask() -> None:
    simulator = PaperExecutionSimulator(seed=7)
    for _ in range(20):
        fill = simulator.fill_market_order(
            order_id=uuid4(),
            side=Side.BUY,
            remaining_quantity=Decimal("10"),
            market=MARKET,
        )
        assert fill.price >= MARKET.ask
        assert fill.quantity <= Decimal("10")
        assert fill.fee >= 0


def test_market_sell_receives_at_or_below_bid() -> None:
    simulator = PaperExecutionSimulator(seed=7)
    fill = simulator.fill_market_order(
        order_id=uuid4(), side=Side.SELL, remaining_quantity=Decimal("10"), market=MARKET
    )
    assert fill.price <= MARKET.bid


def test_limit_buy_fills_only_when_crossed() -> None:
    simulator = PaperExecutionSimulator(seed=1)
    no_fill = simulator.try_fill_limit_order(
        order_id=uuid4(),
        side=Side.BUY,
        remaining_quantity=Decimal("5"),
        limit_price=Decimal("99"),
        market=MARKET,
    )
    assert no_fill is None
    fill = simulator.try_fill_limit_order(
        order_id=uuid4(),
        side=Side.BUY,
        remaining_quantity=Decimal("5"),
        limit_price=Decimal("100.10"),
        market=MARKET,
    )
    assert fill is not None
    assert fill.price == Decimal("100.10")
    assert fill.quantity == Decimal("5")


def test_stop_order_arms_then_fills_as_market() -> None:
    simulator = PaperExecutionSimulator(seed=3)
    order_id = uuid4()
    below_stop = PaperMarketState(bid=Decimal("99"), ask=Decimal("99.1"))
    fill, armed = simulator.evaluate(
        order_id=order_id,
        side=Side.BUY,
        order_type=OrderType.STOP,
        remaining_quantity=Decimal("5"),
        limit_price=None,
        stop_price=Decimal("101"),
        stop_armed=False,
        market=below_stop,
    )
    assert fill is None
    assert armed is False

    above_stop = PaperMarketState(bid=Decimal("101.0"), ask=Decimal("101.2"))
    fill, armed = simulator.evaluate(
        order_id=order_id,
        side=Side.BUY,
        order_type=OrderType.STOP,
        remaining_quantity=Decimal("5"),
        limit_price=None,
        stop_price=Decimal("101"),
        stop_armed=False,
        market=above_stop,
    )
    assert armed is True
    assert fill is not None
    assert fill.price >= above_stop.ask
