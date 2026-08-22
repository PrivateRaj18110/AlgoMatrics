"""Shadow-mode advisory gate.

When a strategy run starts, this logs what AI-CIO *would* advise — whether the
current regime favours the strategy's family, and which of the run's instruments
today's ranking would exclude — **without changing anything**. It never mutates
run state and never places or blocks an order.

Turning these opinions into real behaviour (actually suspending a strategy or
skipping a ticker) is a separate, later change, and the source blueprint is
explicit that nothing is trusted in production without 30+ days of shadow
validation first. This class produces exactly the log signal that review needs.
"""

from __future__ import annotations

import structlog

from algo_platform.modules.market_intel.application.client import AicioClient
from algo_platform.modules.market_intel.domain.regime import StrategyFamily, is_favourable

logger = structlog.get_logger("market_intel.shadow_gate")

# Maps a built-in strategy's entry point to a behavioural family. Uploaded
# strategies are intentionally absent → UNKNOWN → the gate holds no opinion.
_BUILTIN_FAMILIES: dict[str, StrategyFamily] = {
    "sma_crossover": StrategyFamily.MOMENTUM,
    "rsi_reversion": StrategyFamily.MEAN_REVERSION,
    "momentum_breakout": StrategyFamily.MOMENTUM,
}

# A whole-universe read; AI-CIO's universe is ~176 names, so this covers it.
_UNIVERSE_SCAN = 1000


def family_for(entry_point: str, source: str) -> StrategyFamily:
    if source != "builtin":
        return StrategyFamily.UNKNOWN
    for key, family in _BUILTIN_FAMILIES.items():
        if key in entry_point:
            return family
    return StrategyFamily.UNKNOWN


class ShadowGate:
    def __init__(self, client: AicioClient) -> None:
        self._client = client

    async def evaluate(
        self, *, run_id: str, entry_point: str, source: str, symbols: list[str]
    ) -> None:
        """Log the advisory opinion for one run start. Log-only, never raises."""
        try:
            await self._evaluate(
                run_id=run_id, entry_point=entry_point, source=source, symbols=symbols
            )
        except Exception as error:  # advisory side-path must never break run startup
            logger.warning("shadow_gate.evaluate_failed", run_id=run_id, error=type(error).__name__)

    async def _evaluate(
        self, *, run_id: str, entry_point: str, source: str, symbols: list[str]
    ) -> None:
        regime = await self._client.current_regime()
        if regime is None:
            logger.info("shadow_gate.no_data", run_id=run_id, mode="shadow")
            return

        family = family_for(entry_point, source)
        would_suspend = family is not StrategyFamily.UNKNOWN and not is_favourable(
            regime.label, family
        )
        logger.info(
            "shadow_gate.regime_opinion",
            run_id=run_id,
            regime=regime.label,
            family=family.value,
            would_suspend=would_suspend,
            mode="shadow",
        )

        if not symbols:
            return
        ranked = await self._client.rankings(top_n=_UNIVERSE_SCAN)
        if not ranked:
            return
        rank_by_symbol = {row.ticker.upper(): row.rank for row in ranked}
        symbol_ranks = {symbol: rank_by_symbol.get(symbol.upper()) for symbol in symbols}
        would_exclude = [symbol for symbol, rank in symbol_ranks.items() if rank is None]
        logger.info(
            "shadow_gate.ranking_opinion",
            run_id=run_id,
            symbol_ranks=symbol_ranks,
            would_exclude=would_exclude,
            mode="shadow",
        )
