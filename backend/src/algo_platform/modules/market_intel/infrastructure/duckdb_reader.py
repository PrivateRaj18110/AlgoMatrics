"""Read-only projection of the AI-CIO DuckDB into market_intel value objects.

The AI-CIO pipeline owns and writes ``aicio.duckdb``. This reader only ever opens
it ``read_only=True`` with short-lived connections and **degrades to empty/None**
— it never raises — when the file is unconfigured, missing, locked by an in-flight
pipeline write, or malformed. That fail-soft contract mirrors the Yahoo market-info
provider, and the read-only handle is a storage-level guarantee that this path can
never mutate AI-CIO's data. It is a database reader: it cannot place an order.

All SQL here is static and value-parameterised (optional filters use
``(? IS NULL OR col = ?)`` rather than string building), so there is no query
constructed from untrusted input.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import structlog

from algo_platform.modules.market_intel.domain.regime import (
    InstitutionalBias,
    NewsItem,
    OptionsSnapshot,
    RankingDimension,
    RankingRow,
    Regime,
)

logger = structlog.get_logger(__name__)

# Dimension columns, in the order rank.py weights them. Kept as a constant so the
# mapping code and the (static) SELECT below stay in step.
_DIMENSIONS: tuple[str, ...] = (
    "rs_60d",
    "mom_20d",
    "turnover_20d_avg",
    "atr_pct",
    "hv_ratio_10_60",
    "oi_score",
    "if_score",
)
_DEFAULT_NEWS_LIMIT = 20


def _opt_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _opt_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _opt_str(value: Any) -> str | None:
    return None if value is None else str(value)


class AicioDuckDBReader:
    """Fail-soft reader over one AI-CIO DuckDB file."""

    def __init__(self, db_path: Path | None) -> None:
        self._db_path = db_path

    @property
    def db_path(self) -> Path | None:
        return self._db_path

    def _query(self, sql: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]:
        """Run one read-only query. Returns [] on any failure — an unconfigured
        or missing file, a write-lock held by the pipeline, a malformed database,
        or a table that does not exist yet."""
        if self._db_path is None or not self._db_path.exists():
            return []
        con: Any = None
        try:
            con = duckdb.connect(str(self._db_path), read_only=True)
            rows: list[tuple[Any, ...]] = con.execute(sql, params or []).fetchall()
            return rows
        except (duckdb.Error, OSError) as error:
            logger.warning("aicio.read_failed", error=type(error).__name__, path=str(self._db_path))
            return []
        finally:
            if con is not None:
                con.close()

    def latest_regime(self) -> Regime | None:
        rows = self._query(
            "SELECT regime, hmm_confidence, hmm_vol_state, gmm_vol_state, adx_14, "
            "avg_pairwise_corr, breadth_pct_above_ma20, days_since_changepoint, run_date "
            "FROM regime WHERE run_date = (SELECT max(run_date) FROM regime)"
        )
        if rows:
            r = rows[0]
            return Regime(
                label=str(r[0]),
                hmm_confidence=_opt_float(r[1]),
                hmm_vol_state=_opt_str(r[2]),
                gmm_vol_state=_opt_str(r[3]),
                adx_14=_opt_float(r[4]),
                avg_pairwise_corr=_opt_float(r[5]),
                breadth_pct_above_ma20=_opt_float(r[6]),
                days_since_changepoint=_opt_int(r[7]),
                as_of=_opt_str(r[8]),
            )
        # Fallback: no regime table/rows (older pipeline), but every rankings row
        # carries the label, so the bare regime is still recoverable.
        fallback = self._query(
            "SELECT regime, run_date FROM rankings "
            "WHERE run_date = (SELECT max(run_date) FROM rankings) LIMIT 1"
        )
        if fallback:
            return Regime(
                label=str(fallback[0][0]),
                hmm_confidence=None,
                hmm_vol_state=None,
                gmm_vol_state=None,
                adx_14=None,
                avg_pairwise_corr=None,
                breadth_pct_above_ma20=None,
                days_since_changepoint=None,
                as_of=_opt_str(fallback[0][1]),
            )
        return None

    def rankings(self, top_n: int = 20, ticker: str | None = None) -> list[RankingRow]:
        ticker_up = ticker.upper() if ticker else None
        rows = self._query(
            "SELECT run_date, ticker, name, rank, composite_score, regime, "
            "rs_60d, mom_20d, turnover_20d_avg, atr_pct, hv_ratio_10_60, oi_score, if_score "
            "FROM rankings WHERE run_date = (SELECT max(run_date) FROM rankings) "
            "AND (? IS NULL OR ticker = ?) ORDER BY rank LIMIT ?",
            [ticker_up, ticker_up, max(1, top_n)],
        )
        result: list[RankingRow] = []
        for r in rows:
            dimensions = tuple(
                RankingDimension(name=name, value=_opt_float(r[6 + offset]))
                for offset, name in enumerate(_DIMENSIONS)
            )
            result.append(
                RankingRow(
                    run_date=str(r[0]),
                    ticker=str(r[1]),
                    name=_opt_str(r[2]),
                    rank=int(r[3]),
                    composite_score=float(r[4]),
                    regime=str(r[5]),
                    dimensions=dimensions,
                )
            )
        return result

    def news(
        self,
        ticker: str | None = None,
        non_duplicates_only: bool = True,
        limit: int = _DEFAULT_NEWS_LIMIT,
    ) -> list[NewsItem]:
        rows = self._query(
            "SELECT ticker, title, source, link, published_raw, is_duplicate, "
            "sentiment_label, sentiment_score FROM news "
            "WHERE (? IS NULL OR ticker = ?) AND (? OR is_duplicate = FALSE) "
            "ORDER BY fetched_at DESC LIMIT ?",
            [ticker, ticker, not non_duplicates_only, max(1, limit)],
        )
        return [
            NewsItem(
                ticker=str(r[0]),
                title=str(r[1]),
                source=str(r[2]),
                link=str(r[3]),
                published_raw=_opt_str(r[4]),
                is_duplicate=bool(r[5]),
                sentiment_label=_opt_str(r[6]),
                sentiment_score=_opt_float(r[7]),
            )
            for r in rows
        ]

    def options_snapshot(self, ticker: str) -> OptionsSnapshot | None:
        rows = self._query(
            "SELECT ticker, run_date, max_pain, max_pain_dist_pct, pcr_oi, pcr_volume, "
            "iv_skew, atm_iv, oi_score FROM options_features "
            "WHERE ticker = ? AND run_date = (SELECT max(run_date) FROM options_features)",
            [ticker.upper()],
        )
        if not rows:
            return None
        r = rows[0]
        return OptionsSnapshot(
            ticker=str(r[0]),
            run_date=str(r[1]),
            max_pain=_opt_float(r[2]),
            max_pain_dist_pct=_opt_float(r[3]),
            pcr_oi=_opt_float(r[4]),
            pcr_volume=_opt_float(r[5]),
            iv_skew=_opt_float(r[6]),
            atm_iv=_opt_float(r[7]),
            oi_score=_opt_float(r[8]),
        )

    def institutional_flow(self, ticker: str) -> InstitutionalBias | None:
        rows = self._query(
            "SELECT ticker, run_date, net_value, gross_value, n_deals, if_score "
            "FROM institutional_flow "
            "WHERE ticker = ? AND run_date = (SELECT max(run_date) FROM institutional_flow)",
            [ticker.upper()],
        )
        if not rows:
            return None
        r = rows[0]
        return InstitutionalBias(
            ticker=str(r[0]),
            run_date=str(r[1]),
            net_value=_opt_float(r[2]),
            gross_value=_opt_float(r[3]),
            n_deals=_opt_int(r[4]),
            if_score=_opt_float(r[5]) or 0.0,
        )


_reader: AicioDuckDBReader | None = None


def get_aicio_reader(db_path: Path | None) -> AicioDuckDBReader:
    """Process-wide reader, rebuilt only if the configured path changes."""
    global _reader
    if _reader is None or _reader.db_path != db_path:
        _reader = AicioDuckDBReader(db_path)
    return _reader
