from algo_strategy_sdk.context import StrategyContext
from algo_strategy_sdk.events import Candle, OrderUpdate, PositionUpdate, Signal, Tick


class Strategy:
    """Stable SDK contract. Override only the callbacks a strategy needs.

    Every hook is optional by design; the runtime invokes whichever callbacks
    the subclass implements. Subclasses must not assume any hook is abstract.
    """

    async def initialize(self, context: StrategyContext) -> None:
        pass

    async def on_tick(self, tick: Tick, context: StrategyContext) -> None:
        pass

    async def on_candle(self, candle: Candle, context: StrategyContext) -> None:
        pass

    async def on_signal(self, signal: Signal, context: StrategyContext) -> None:
        pass

    async def on_order_update(self, update: OrderUpdate, context: StrategyContext) -> None:
        pass

    async def on_position_update(self, update: PositionUpdate, context: StrategyContext) -> None:
        pass

    async def shutdown(self, context: StrategyContext) -> None:
        pass
