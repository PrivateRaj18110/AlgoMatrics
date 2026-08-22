"""Market-intelligence value objects and the regime→strategy favourability rule.

Framework-free: this is the context's public contract, projected onto by the
outer layers. The data originates in the AI-CIO research pipeline and is purely
advisory — none of these objects, and nothing that consumes them, reaches a
broker or changes a position.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class StrategyFamily(StrEnum):
    """Broad behavioural family a strategy belongs to, for regime matching.

    ``UNKNOWN`` covers uploaded strategies whose behaviour we cannot classify;
    the gate deliberately holds no opinion on those.
    """

    MOMENTUM = "momentum"
    MEAN_REVERSION = "mean_reversion"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Regime:
    """The market regime for the latest AI-CIO run, with ensemble diagnostics.

    Diagnostics are optional: a DuckDB written before the regime table existed
    (or a degenerate fit) yields the label only, with the rest ``None``.
    """

    label: str
    hmm_confidence: float | None
    hmm_vol_state: str | None
    gmm_vol_state: str | None
    adx_14: float | None
    avg_pairwise_corr: float | None
    breadth_pct_above_ma20: float | None
    days_since_changepoint: int | None
    as_of: str | None


@dataclass(frozen=True, slots=True)
class RankingDimension:
    """One weighted input behind a composite score (``None`` if not computed)."""

    name: str
    value: float | None


@dataclass(frozen=True, slots=True)
class RankingRow:
    """A ticker's place in the latest cross-sectional ranking, with the raw
    dimension breakdown that produced its composite score."""

    run_date: str
    ticker: str
    name: str | None
    rank: int
    composite_score: float
    regime: str
    dimensions: tuple[RankingDimension, ...]


@dataclass(frozen=True, slots=True)
class NewsItem:
    ticker: str
    title: str
    source: str
    link: str
    published_raw: str | None
    is_duplicate: bool
    sentiment_label: str | None
    sentiment_score: float | None


@dataclass(frozen=True, slots=True)
class OptionsSnapshot:
    ticker: str
    run_date: str
    max_pain: float | None
    max_pain_dist_pct: float | None
    pcr_oi: float | None
    pcr_volume: float | None
    iv_skew: float | None
    atm_iv: float | None
    oi_score: float | None


@dataclass(frozen=True, slots=True)
class InstitutionalBias:
    ticker: str
    run_date: str
    net_value: float | None
    gross_value: float | None
    n_deals: int | None
    if_score: float


# Which strategy families each regime label favours. Derived from the intent
# behind AI-CIO's own REGIME_WEIGHTS (config.py): trending / risk_on regimes
# reward momentum and relative strength; low/normal-vol ranging regimes reward
# mean reversion; and "no clear edge" regimes (ranging_high, risk_off, the
# recovery transition) favour neither — the doc's guidance there is to reduce
# size / stand aside, so the advisory view is "suspend both".
_FAVOURABLE: dict[str, frozenset[StrategyFamily]] = {
    "trending_low": frozenset({StrategyFamily.MOMENTUM}),
    "trending_normal": frozenset({StrategyFamily.MOMENTUM}),
    "trending_high": frozenset({StrategyFamily.MOMENTUM}),
    "ranging_low": frozenset({StrategyFamily.MEAN_REVERSION}),
    "ranging_normal": frozenset({StrategyFamily.MEAN_REVERSION}),
    "ranging_high": frozenset(),
    "risk_on": frozenset({StrategyFamily.MOMENTUM}),
    "risk_off": frozenset(),
    "recovery_transition": frozenset(),
}


def is_favourable(regime_label: str, family: StrategyFamily) -> bool:
    """Is ``family`` advised for ``regime_label``?

    Fail-open by design: this is advice, not a control. An ``UNKNOWN`` family or
    an unrecognised regime label (e.g. one added upstream later) returns ``True``
    so the advisory layer never *quietly* discourages a strategy it cannot reason
    about — a real suspension would be an explicit, reviewed decision elsewhere.
    """
    if family is StrategyFamily.UNKNOWN:
        return True
    if regime_label not in _FAVOURABLE:
        return True
    return family in _FAVOURABLE[regime_label]
