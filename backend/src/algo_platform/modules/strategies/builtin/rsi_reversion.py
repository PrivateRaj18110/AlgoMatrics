"""Built-in strategy: RSI mean reversion.

Buys oversold conditions and exits when the RSI normalizes; optionally
shorts overbought conditions.
"""

from __future__ import annotations

from collections import deque
from decimal import Decimal

from algo_strategy_sdk.context import StrategyContext
from algo_strategy_sdk.events import Candle
from algo_strategy_sdk.strategy import Strategy

MANIFEST = {
    "name": "RSI Mean Reversion",
    "entry_point": "algo_platform.modules.strategies.builtin.rsi_reversion:RsiReversion",
    "description": "Buys oversold RSI readings and exits at the midline.",
    "required_data": ["candles"],
    "parameters": [
        {
            "name": "period",
            "type": "int",
            "default": 14,
            "min": 2,
            "max": 100,
            "description": "RSI lookback",
        },
        {
            "name": "oversold",
            "type": "float",
            "default": 30,
            "min": 5,
            "max": 49,
            "description": "Entry threshold",
        },
        {
            "name": "overbought",
            "type": "float",
            "default": 70,
            "min": 51,
            "max": 95,
            "description": "Short entry / exit threshold",
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
            "description": "Short overbought conditions",
        },
    ],
}


class RsiReversion(Strategy):
    def __init__(self) -> None:
        self._closes: dict[str, deque[Decimal]] = {}

    def _rsi(self, closes: list[Decimal], period: int) -> Decimal | None:
        if len(closes) <= period:
            return None
        gains = Decimal("0")
        losses = Decimal("0")
        for previous, current in zip(closes[-period - 1 : -1], closes[-period:], strict=True):
            change = current - previous
            if change > 0:
                gains += change
            else:
                losses -= change
        if losses == 0:
            return Decimal("100")
        rs = gains / losses
        return Decimal("100") - (Decimal("100") / (Decimal("1") + rs))

    async def on_candle(self, candle: Candle, context: StrategyContext) -> None:
        period = int(context.params["period"])
        closes = self._closes.setdefault(candle.instrument, deque(maxlen=period + 1))
        closes.append(candle.close)
        rsi = self._rsi(list(closes), period)
        if rsi is None:
            return

        oversold = Decimal(str(context.params["oversold"]))
        overbought = Decimal(str(context.params["overbought"]))
        quantity = Decimal(str(context.params["quantity"]))
        allow_short = bool(context.params["allow_short"])
        position = await context.get_position(candle.instrument)

        if rsi <= oversold and position <= 0:
            size = quantity + (abs(position) if position < 0 else Decimal("0"))
            await context.emit_signal(
                name="rsi_oversold", instrument=candle.instrument, strength=rsi / 100
            )
            await context.request_order(instrument=candle.instrument, side="buy", quantity=size)
        elif rsi >= overbought:
            if position > 0:
                await context.emit_signal(
                    name="rsi_overbought", instrument=candle.instrument, strength=rsi / 100
                )
                await context.request_order(
                    instrument=candle.instrument, side="sell", quantity=position
                )
            elif allow_short and position == 0:
                await context.emit_signal(
                    name="rsi_short", instrument=candle.instrument, strength=rsi / 100
                )
                await context.request_order(
                    instrument=candle.instrument, side="sell", quantity=quantity
                )
        elif position < 0 and rsi <= Decimal("50"):
            await context.request_order(
                instrument=candle.instrument, side="buy", quantity=abs(position)
            )
