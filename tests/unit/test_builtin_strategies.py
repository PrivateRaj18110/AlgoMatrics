"""Unit tests for the first-party built-in strategies.

A capturing fake ``StrategyContext`` records signals/orders/logs so the pure
candle logic (indicator maths and crossover/threshold rules) is exercised
without the runtime, engine, or database.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal

import pytest
from algo_strategy_sdk.context import ParamValue
from algo_strategy_sdk.events import Candle

from algo_platform.modules.strategies.builtin.momentum_breakout import MomentumBreakout
from algo_platform.modules.strategies.builtin.rsi_reversion import RsiReversion
from algo_platform.modules.strategies.builtin.sma_crossover import SmaCrossover
from algo_platform.shared.domain.types import utc_now


class FakeContext:
    def __init__(self, params: Mapping[str, ParamValue], position: Decimal = Decimal("0")) -> None:
        self._params = params
        self._position = position
        self.orders: list[tuple[str, str, Decimal]] = []
        self.signals: list[str] = []
        self.logs: list[tuple[str, str]] = []

    @property
    def now(self) -> datetime:
        return utc_now()

    @property
    def params(self) -> Mapping[str, ParamValue]:
        return self._params

    async def subscribe_ticks(self, *instruments: str) -> None: ...

    async def subscribe_candles(self, instrument: str, *timeframes: str) -> None: ...

    async def emit_signal(
        self,
        *,
        name: str,
        instrument: str,
        strength: Decimal,
        attributes: dict[str, str | int | float | bool] | None = None,
    ) -> None:
        self.signals.append(name)

    async def request_order(
        self,
        *,
        instrument: str,
        side: str,
        quantity: Decimal,
        order_type: str = "market",
        limit_price: Decimal | None = None,
        stop_price: Decimal | None = None,
    ) -> str:
        self.orders.append((side, instrument, quantity))
        # Immediate-fill model so net position tracks across candles.
        self._position += quantity if side == "buy" else -quantity
        return "cid"

    async def cancel_order(self, client_order_id: str) -> None: ...

    async def get_position(self, instrument: str) -> Decimal:
        return self._position

    async def log(self, message: str, *, level: str = "info") -> None:
        self.logs.append((level, message))

    def state_get(self, key: str, default: object = None) -> object:
        return default

    async def state_set(self, key: str, value: object) -> None: ...


def _candle(close: str, *, high: str | None = None, low: str | None = None) -> Candle:
    price = Decimal(close)
    return Candle(
        instrument="RELIANCE",
        timeframe="1m",
        timestamp=utc_now(),
        open=price,
        high=Decimal(high) if high else price,
        low=Decimal(low) if low else price,
        close=price,
        volume=Decimal("1000"),
    )


async def _feed(strategy: object, context: FakeContext, closes: list[str]) -> None:
    for close in closes:
        await strategy.on_candle(_candle(close), context)  # type: ignore[attr-defined]


# ------------------------------ SMA crossover -------------------------------


class TestSmaCrossover:
    def _params(self, **over: ParamValue) -> dict[str, ParamValue]:
        base: dict[str, ParamValue] = {
            "fast_period": 2,
            "slow_period": 3,
            "quantity": 1,
            "allow_short": False,
        }
        base.update(over)
        return base

    async def test_bullish_cross_places_buy(self) -> None:
        strategy = SmaCrossover()
        context = FakeContext(self._params())
        await _feed(strategy, context, ["10", "10", "10", "13"])
        assert context.orders == [("buy", "RELIANCE", Decimal("1"))]
        assert "sma_cross_up" in context.signals

    async def test_bearish_cross_closes_long(self) -> None:
        strategy = SmaCrossover()
        context = FakeContext(self._params(), position=Decimal("1"))
        # Establish a positive diff, then flip negative to cross down.
        await _feed(strategy, context, ["10", "12", "14", "8"])
        assert context.orders == [("sell", "RELIANCE", Decimal("1"))]

    async def test_invalid_periods_warn_and_skip(self) -> None:
        strategy = SmaCrossover()
        context = FakeContext(self._params(fast_period=5, slow_period=3))
        await _feed(strategy, context, ["10", "11", "12", "13", "14"])
        assert context.orders == []
        assert any(level == "warning" for level, _ in context.logs)

    async def test_insufficient_history_no_order(self) -> None:
        strategy = SmaCrossover()
        context = FakeContext(self._params())
        await _feed(strategy, context, ["10", "11"])
        assert context.orders == []


# ------------------------------ RSI reversion -------------------------------


class TestRsiReversion:
    def _params(self, **over: ParamValue) -> dict[str, ParamValue]:
        base: dict[str, ParamValue] = {
            "period": 3,
            "oversold": 30,
            "overbought": 70,
            "quantity": 2,
            "allow_short": False,
        }
        base.update(over)
        return base

    async def test_oversold_places_buy(self) -> None:
        strategy = RsiReversion()
        context = FakeContext(self._params())
        # Strictly falling closes drive RSI to 0 (all losses).
        await _feed(strategy, context, ["100", "90", "80", "70"])
        assert context.orders == [("buy", "RELIANCE", Decimal("2"))]
        assert "rsi_oversold" in context.signals

    async def test_overbought_closes_long(self) -> None:
        strategy = RsiReversion()
        context = FakeContext(self._params(), position=Decimal("2"))
        # Strictly rising closes drive RSI to 100 (all gains).
        await _feed(strategy, context, ["70", "80", "90", "100"])
        assert context.orders == [("sell", "RELIANCE", Decimal("2"))]

    async def test_insufficient_history_no_order(self) -> None:
        strategy = RsiReversion()
        context = FakeContext(self._params())
        await _feed(strategy, context, ["100", "90"])
        assert context.orders == []


# ---------------------------- Momentum breakout -----------------------------


class TestMomentumBreakout:
    def _params(self, **over: ParamValue) -> dict[str, ParamValue]:
        base: dict[str, ParamValue] = {
            "channel_period": 3,
            "exit_period": 2,
            "quantity": 1,
        }
        base.update(over)
        return base

    async def test_breakout_above_channel_buys(self) -> None:
        strategy = MomentumBreakout()
        context = FakeContext(self._params())
        await _feed(strategy, context, ["10", "11", "12", "20"])
        assert context.orders == [("buy", "RELIANCE", Decimal("1"))]
        assert "breakout_up" in context.signals

    async def test_break_below_exit_channel_sells(self) -> None:
        strategy = MomentumBreakout()
        context = FakeContext(self._params(), position=Decimal("1"))
        await _feed(strategy, context, ["20", "19", "18", "5"])
        assert context.orders == [("sell", "RELIANCE", Decimal("1"))]

    async def test_no_breakout_no_order(self) -> None:
        strategy = MomentumBreakout()
        context = FakeContext(self._params())
        await _feed(strategy, context, ["10", "10", "10", "10"])
        assert context.orders == []


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
