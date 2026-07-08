"""Built-in strategy: Donchian-channel momentum breakout."""

from __future__ import annotations

from collections import deque
from decimal import Decimal

from algo_strategy_sdk.context import StrategyContext
from algo_strategy_sdk.events import Candle
from algo_strategy_sdk.strategy import Strategy

MANIFEST = {
    "name": "Momentum Breakout",
    "entry_point": ("algo_platform.modules.strategies.builtin.momentum_breakout:MomentumBreakout"),
    "description": "Buys breakouts above the recent high channel; exits below the low channel.",
    "required_data": ["candles"],
    "parameters": [
        {
            "name": "channel_period",
            "type": "int",
            "default": 20,
            "min": 5,
            "max": 200,
            "description": "Lookback for the breakout channel",
        },
        {
            "name": "exit_period",
            "type": "int",
            "default": 10,
            "min": 3,
            "max": 100,
            "description": "Lookback for the exit channel",
        },
        {
            "name": "quantity",
            "type": "float",
            "default": 1,
            "min": 0.0001,
            "max": 100000,
            "description": "Order size per signal",
        },
    ],
}


class MomentumBreakout(Strategy):
    def __init__(self) -> None:
        self._highs: dict[str, deque[Decimal]] = {}
        self._lows: dict[str, deque[Decimal]] = {}

    async def on_candle(self, candle: Candle, context: StrategyContext) -> None:
        channel_period = int(context.params["channel_period"])
        exit_period = int(context.params["exit_period"])
        highs = self._highs.setdefault(candle.instrument, deque(maxlen=channel_period))
        lows = self._lows.setdefault(candle.instrument, deque(maxlen=channel_period))

        prior_high = max(highs) if len(highs) >= channel_period else None
        prior_low = min(list(lows)[-exit_period:]) if len(lows) >= exit_period else None
        highs.append(candle.high)
        lows.append(candle.low)

        quantity = Decimal(str(context.params["quantity"]))
        position = await context.get_position(candle.instrument)

        if prior_high is not None and candle.close > prior_high and position == 0:
            await context.emit_signal(
                name="breakout_up", instrument=candle.instrument, strength=Decimal("1")
            )
            await context.request_order(instrument=candle.instrument, side="buy", quantity=quantity)
        elif prior_low is not None and candle.close < prior_low and position > 0:
            await context.emit_signal(
                name="breakout_exit", instrument=candle.instrument, strength=Decimal("1")
            )
            await context.request_order(
                instrument=candle.instrument, side="sell", quantity=position
            )
