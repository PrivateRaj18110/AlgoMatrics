"""AicioClient — the single thin entry point other code uses to read AI-CIO.

Rather than scatter DuckDB access around the codebase, everything goes through this
facade. It wraps the synchronous reader in ``asyncio.to_thread`` so callers (the API
routes and the trading engine) never block their event loop on a file read, and it
layers the regime→family favourability judgement on top of the raw data.

Adapted from the source blueprint's sketch: the methods keep the blueprint's names
but return this platform's typed value objects instead of pandas DataFrames (the
backend deliberately carries no pandas dependency). It is read-only and advisory.
"""

from __future__ import annotations

import asyncio

from algo_platform.modules.market_intel.domain.regime import (
    InstitutionalBias,
    NewsItem,
    OptionsSnapshot,
    RankingRow,
    Regime,
    StrategyFamily,
    is_favourable,
)
from algo_platform.modules.market_intel.infrastructure.duckdb_reader import AicioDuckDBReader


def family_from_type(strategy_type: str) -> StrategyFamily:
    """Coerce a free-form strategy-type string (e.g. ``"mean_reversion"``) to a
    known family, falling back to ``UNKNOWN`` for anything unrecognised."""
    try:
        return StrategyFamily(strategy_type.strip().lower())
    except ValueError:
        return StrategyFamily.UNKNOWN


class AicioClient:
    def __init__(self, reader: AicioDuckDBReader) -> None:
        self._reader = reader

    async def current_regime(self) -> Regime | None:
        return await asyncio.to_thread(self._reader.latest_regime)

    async def rankings(self, top_n: int = 20, ticker: str | None = None) -> list[RankingRow]:
        return await asyncio.to_thread(self._reader.rankings, top_n, ticker)

    async def is_favorable_regime(self, strategy_type: str) -> bool:
        """Whether the current regime favours ``strategy_type``. With no AI-CIO
        data available this returns ``True`` (no opinion) — advisory, fail-open."""
        regime = await self.current_regime()
        if regime is None:
            return True
        return is_favourable(regime.label, family_from_type(strategy_type))

    async def recent_news(
        self, ticker: str | None = None, non_duplicates_only: bool = True
    ) -> list[NewsItem]:
        """Recent headlines. ``ticker=None`` returns cross-universe news for the
        dashboard feed (a benign superset of the blueprint's per-ticker method)."""
        return await asyncio.to_thread(self._reader.news, ticker, non_duplicates_only)

    async def options_snapshot(self, ticker: str) -> OptionsSnapshot | None:
        return await asyncio.to_thread(self._reader.options_snapshot, ticker)

    async def institutional_flow(self, ticker: str) -> InstitutionalBias | None:
        """The full bulk/block-deal row for a ticker, or ``None`` if it had no
        deal on the latest run."""
        return await asyncio.to_thread(self._reader.institutional_flow, ticker)

    async def institutional_bias(self, ticker: str) -> float:
        """Bulk/block-deal bias score for a ticker; a neutral ``0.0`` when the
        ticker had no deal (AI-CIO's own sparse-flow convention)."""
        flow = await self.institutional_flow(ticker)
        return flow.if_score if flow is not None else 0.0
