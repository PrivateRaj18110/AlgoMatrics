"""Market pulse: breadth, sector rotation, trend and volatility regimes.

Pure functions over prices the caller already fetched. Every number returned
is derived from real quotes with a stated method; nothing is simulated.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise
from typing import Any


@dataclass(frozen=True, slots=True)
class Quote:
    symbol: str
    name: str | None
    price: float | None
    previous_close: float | None
    day_high: float | None
    day_low: float | None
    year_high: float | None
    year_low: float | None
    volume: float | None
    as_of: int | None  # unix seconds from the source

    @property
    def change_pct(self) -> float | None:
        if self.price is None or not self.previous_close:
            return None
        return (self.price - self.previous_close) / self.previous_close * 100


@dataclass(frozen=True, slots=True)
class Breadth:
    advances: int
    declines: int
    unchanged: int
    ratio: float | None  # advances / declines
    pct_advancing: float | None
    near_year_high: int
    near_year_low: int


def breadth(quotes: Sequence[Quote], *, flat_band_pct: float = 0.05) -> Breadth:
    changes = [q.change_pct for q in quotes if q.change_pct is not None]
    advances = sum(1 for c in changes if c > flat_band_pct)
    declines = sum(1 for c in changes if c < -flat_band_pct)
    unchanged = len(changes) - advances - declines
    near_high = sum(1 for q in quotes if q.price and q.year_high and q.price >= 0.98 * q.year_high)
    near_low = sum(1 for q in quotes if q.price and q.year_low and q.price <= 1.02 * q.year_low)
    return Breadth(
        advances=advances,
        declines=declines,
        unchanged=unchanged,
        ratio=round(advances / declines, 2) if declines else None,
        pct_advancing=round(advances / len(changes) * 100, 1) if changes else None,
        near_year_high=near_high,
        near_year_low=near_low,
    )


@dataclass(frozen=True, slots=True)
class SectorMove:
    sector: str
    change_pct: float
    members: int
    advancing: int
    leader: str | None
    laggard: str | None


def sector_performance(
    quotes: Sequence[Quote], sector_of: dict[str, str], weight_of: dict[str, float]
) -> list[SectorMove]:
    """Market-cap weighted change per sector (equal weight when caps are unknown)."""
    groups: dict[str, list[tuple[Quote, float]]] = defaultdict(list)
    for quote in quotes:
        if quote.change_pct is None:
            continue
        groups[sector_of.get(quote.symbol, "Other")].append(
            (quote, weight_of.get(quote.symbol) or 1.0)
        )
    moves: list[SectorMove] = []
    for sector, members in groups.items():
        total_weight = sum(w for _, w in members) or 1.0
        change = sum((q.change_pct or 0.0) * w for q, w in members) / total_weight
        ranked = sorted(members, key=lambda m: m[0].change_pct or 0.0)
        moves.append(
            SectorMove(
                sector=sector,
                change_pct=round(change, 2),
                members=len(members),
                advancing=sum(1 for q, _ in members if (q.change_pct or 0) > 0),
                leader=ranked[-1][0].symbol if ranked else None,
                laggard=ranked[0][0].symbol if ranked else None,
            )
        )
    return sorted(moves, key=lambda m: m.change_pct, reverse=True)


def sma(values: Sequence[float], window: int) -> float | None:
    if len(values) < window or window <= 0:
        return None
    return sum(values[-window:]) / window


def rsi(values: Sequence[float], period: int = 14) -> float | None:
    """Wilder's RSI on closing prices."""
    if len(values) <= period:
        return None
    deltas = [current - previous for previous, current in pairwise(values)]
    seed = deltas[:period]
    avg_gain = sum(max(d, 0.0) for d in seed) / period
    avg_loss = sum(max(-d, 0.0) for d in seed) / period
    for delta in deltas[period:]:
        avg_gain = (avg_gain * (period - 1) + max(delta, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-delta, 0.0)) / period
    if avg_loss == 0:
        return 100.0
    return round(100 - 100 / (1 + avg_gain / avg_loss), 1)


def pct_return(values: Sequence[float], periods: int) -> float | None:
    if len(values) <= periods or not values[-periods - 1]:
        return None
    return round((values[-1] / values[-periods - 1] - 1) * 100, 2)


@dataclass(frozen=True, slots=True)
class TrendRegime:
    label: str  # "Uptrend" | "Downtrend" | "Range-bound" | "Unknown"
    price: float | None
    sma20: float | None
    sma50: float | None
    sma200: float | None
    rsi14: float | None
    return_5d: float | None
    return_20d: float | None
    explanation: str


def trend_regime(closes: Sequence[float]) -> TrendRegime:
    price = closes[-1] if closes else None
    s20, s50, s200 = sma(closes, 20), sma(closes, 50), sma(closes, 200)
    if price is None or s50 is None or s200 is None:
        label, why = "Unknown", "Not enough price history to classify the trend."
    elif price > s50 > s200:
        label, why = "Uptrend", "Price is above its 50-day average, which is above the 200-day."
    elif price < s50 < s200:
        label, why = "Downtrend", "Price is below its 50-day average, which is below the 200-day."
    else:
        label, why = "Range-bound", "Price and its 50/200-day averages are not aligned."
    return TrendRegime(
        label=label,
        price=price,
        sma20=round(s20, 2) if s20 else None,
        sma50=round(s50, 2) if s50 else None,
        sma200=round(s200, 2) if s200 else None,
        rsi14=rsi(closes),
        return_5d=pct_return(closes, 5),
        return_20d=pct_return(closes, 20),
        explanation=why,
    )


@dataclass(frozen=True, slots=True)
class VolatilityRegime:
    label: str
    vix: float | None
    explanation: str


# India VIX bands, as commonly read by Indian derivatives desks.
_VIX_BANDS: tuple[tuple[float, str, str], ...] = (
    (13.0, "Calm", "Option premiums are cheap; ranges tend to be narrow."),
    (18.0, "Normal", "Volatility is in its usual range."),
    (24.0, "Elevated", "Expect wider intraday swings; size positions down."),
    (float("inf"), "Stressed", "Fear is high: gaps and sharp reversals are likely."),
)


def volatility_regime(vix: float | None) -> VolatilityRegime:
    if vix is None:
        return VolatilityRegime("Unknown", None, "India VIX is not available right now.")
    for ceiling, label, explanation in _VIX_BANDS:
        if vix < ceiling:
            return VolatilityRegime(label, round(vix, 2), explanation)
    raise AssertionError("unreachable: the last band is unbounded")


@dataclass(frozen=True, slots=True)
class InstitutionalFlow:
    trade_date: str
    fii_net: float | None
    dii_net: float | None
    fii_buy: float | None
    fii_sell: float | None
    dii_buy: float | None
    dii_sell: float | None


def parse_fii_dii(rows: Any) -> InstitutionalFlow | None:
    """NSE's provisional cash-market figures (₹ crore)."""
    if not isinstance(rows, list):
        return None
    by_category: dict[str, dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("category"), str):
            key = "FII" if "FII" in row["category"].upper() else "DII"
            by_category[key] = row

    def value(category: str, field_name: str) -> float | None:
        raw = by_category.get(category, {}).get(field_name)
        try:
            return float(str(raw).replace(",", ""))
        except (TypeError, ValueError):
            return None

    trade_date = str((by_category.get("FII") or by_category.get("DII") or {}).get("date") or "")
    if not trade_date:
        return None
    return InstitutionalFlow(
        trade_date=trade_date,
        fii_net=value("FII", "netValue"),
        dii_net=value("DII", "netValue"),
        fii_buy=value("FII", "buyValue"),
        fii_sell=value("FII", "sellValue"),
        dii_buy=value("DII", "buyValue"),
        dii_sell=value("DII", "sellValue"),
    )
