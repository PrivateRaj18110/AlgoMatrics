"""Built-in strategy: simple-moving-average crossover.

Goes long when the fast SMA crosses above the slow SMA, exits (and may go
short if allowed) on the opposite cross. First-party, reviewed, in-process.
"""

from __future__ import annotations

from collections import deque
from decimal import Decimal

from algo_strategy_sdk.context import StrategyContext
from algo_strategy_sdk.events import Candle
from algo_strategy_sdk.strategy import Strategy

MANIFEST = {
    "name": "SMA Crossover",
    "entry_point": "algo_platform.modules.strategies.builtin.sma_crossover:SmaCrossover",
    "description": "Fast/slow moving-average crossover with fixed order size.",
    "required_data": ["candles"],
    "parameters": [
        {
            "name": "fast_period",
            "type": "int",
            "default": 9,
            "min": 2,
            "max": 200,
            "description": "Fast SMA lookback in candles",
        },
        {
            "name": "slow_period",
            "type": "int",
            "default": 21,
            "min": 3,
            "max": 400,
            "description": "Slow SMA lookback in candles",
        },
        {
            "name": "quantity",
            "type": "float",
            "default": 1,
            "min": 0.0001,
            "max": 100000,
            "description": "Order size per signal",
        },
        {
            "name": "allow_short",
            "type": "bool",
            "default": False,
            "description": "Open short positions on bearish crosses",
        },
    ],
}


class SmaCrossover(Strategy):
    def __init__(self) -> None:
        self._closes: dict[str, deque[Decimal]] = {}
        self._last_diff: dict[str, Decimal | None] = {}

    async def initialize(self, context: StrategyContext) -> None:
        await context.log("SMA crossover initialized")

    async def on_candle(self, candle: Candle, context: StrategyContext) -> None:
        fast = int(context.params["fast_period"])
        slow = int(context.params["slow_period"])
        if fast >= slow:
            await context.log("fast_period must be below slow_period", level="warning")
            return
        closes = self._closes.setdefault(candle.instrument, deque(maxlen=slow))
        closes.append(candle.close)
        if len(closes) < slow:
            return
        prices = list(closes)
        fast_sma = sum(prices[-fast:], Decimal("0")) / fast
        slow_sma = sum(prices, Decimal("0")) / slow
        diff = fast_sma - slow_sma
        previous = self._last_diff.get(candle.instrument)
        self._last_diff[candle.instrument] = diff
        if previous is None:
            return

        quantity = Decimal(str(context.params["quantity"]))
        allow_short = bool(context.params["allow_short"])
        position = await context.get_position(candle.instrument)

        crossed_up = previous <= 0 < diff
        crossed_down = previous >= 0 > diff
        if crossed_up and position <= 0:
            size = quantity + (abs(position) if position < 0 else Decimal("0"))
            await context.emit_signal(
                name="sma_cross_up", instrument=candle.instrument, strength=Decimal("1")
            )
            await context.request_order(instrument=candle.instrument, side="buy", quantity=size)
        elif crossed_down and position >= 0:
            close_size = abs(position) if position > 0 else Decimal("0")
            size = close_size + (quantity if allow_short else Decimal("0"))
            if size > 0:
                await context.emit_signal(
                    name="sma_cross_down",
                    instrument=candle.instrument,
                    strength=Decimal("1"),
                )
                await context.request_order(
                    instrument=candle.instrument, side="sell", quantity=size
                )
