"""NSE pre-open auction: parsing and the day's algorithmic watchlist.

The pre-open session (09:00-09:08 IST) discovers each stock's opening price
(the IEP) from real orders. Two facts from it carry signal for the first hour:

- the gap: IEP vs the previous close;
- the order-book imbalance: unexecuted buy vs sell quantity left at the IEP.

A gap backed by same-side imbalance tends to extend; a gap leaning against the
imbalance is a reversal candidate. These screens rank those situations. They are
mechanical and explainable - every pick carries its reasons - and they are not
investment advice.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from algo_platform.modules.market_insights.domain.sectors import sector_for

MIN_GAP_PCT = 1.0
MIN_IMBALANCE = 0.2
NEAR_HIGH_RATIO = 0.97
PICKS_PER_SCREEN = 6


@dataclass(frozen=True, slots=True)
class PreOpenStock:
    symbol: str
    sector: str
    iep: float
    previous_close: float
    change: float
    change_pct: float
    final_quantity: int
    turnover: float
    market_cap: float
    year_high: float | None
    year_low: float | None
    buy_quantity: int
    sell_quantity: int

    @property
    def imbalance(self) -> float:
        """(buy - sell) / (buy + sell) in [-1, 1]; 0 when the book is empty."""
        total = self.buy_quantity + self.sell_quantity
        return 0.0 if total == 0 else (self.buy_quantity - self.sell_quantity) / total

    @property
    def near_year_high(self) -> bool:
        return bool(self.year_high) and self.iep >= NEAR_HIGH_RATIO * float(self.year_high or 0)

    @property
    def near_year_low(self) -> bool:
        return bool(self.year_low) and self.iep <= float(self.year_low or 0) / NEAR_HIGH_RATIO


@dataclass(frozen=True, slots=True)
class PreOpenSnapshot:
    as_of: datetime | None
    trade_date: date | None
    advances: int
    declines: int
    unchanged: int
    total_traded_value: float
    stocks: list[PreOpenStock]


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_nse_timestamp(raw: Any) -> datetime | None:
    """NSE writes '18-Sep-2026 09:08:37' (IST, naive)."""
    if not isinstance(raw, str):
        return None
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%Y"):
        try:
            return datetime.strptime(raw.strip(), fmt)
        except ValueError:
            continue
    return None


def parse_preopen(payload: dict[str, Any]) -> PreOpenSnapshot:
    stocks: list[PreOpenStock] = []
    for row in payload.get("data") or []:
        meta = row.get("metadata") or {}
        book = ((row.get("detail") or {}).get("preOpenMarket")) or {}
        symbol = str(meta.get("symbol") or "").strip()
        if not symbol:
            continue
        stocks.append(
            PreOpenStock(
                symbol=symbol,
                sector=sector_for(symbol),
                iep=_num(meta.get("iep") or meta.get("lastPrice")),
                previous_close=_num(meta.get("previousClose")),
                change=_num(meta.get("change")),
                change_pct=_num(meta.get("pChange")),
                final_quantity=int(_num(meta.get("finalQuantity"))),
                turnover=_num(meta.get("totalTurnover")),
                market_cap=_num(meta.get("marketCap")),
                year_high=_num(meta.get("yearHigh")) or None,
                year_low=_num(meta.get("yearLow")) or None,
                buy_quantity=int(_num(book.get("totalBuyQuantity"))),
                sell_quantity=int(_num(book.get("totalSellQuantity"))),
            )
        )
    as_of = parse_nse_timestamp(payload.get("timestamp"))
    return PreOpenSnapshot(
        as_of=as_of,
        trade_date=as_of.date() if as_of else None,
        advances=int(_num(payload.get("advances"))),
        declines=int(_num(payload.get("declines"))),
        unchanged=int(_num(payload.get("unchanged"))),
        total_traded_value=_num(payload.get("totalTradedValue")),
        stocks=stocks,
    )


@dataclass(frozen=True, slots=True)
class Pick:
    symbol: str
    sector: str
    iep: float
    change_pct: float
    imbalance: float
    turnover: float
    score: float
    bias: str  # "long" | "short" | "watch"
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Screen:
    key: str
    title: str
    description: str
    picks: list[Pick]


def _liquidity(stock: PreOpenStock) -> float:
    # log-scaled so a mega-cap's turnover does not drown every other signal
    return math.log10(max(stock.turnover, 1.0))


def _pick(stock: PreOpenStock, *, score: float, bias: str, reasons: list[str]) -> Pick:
    return Pick(
        symbol=stock.symbol,
        sector=stock.sector,
        iep=stock.iep,
        change_pct=round(stock.change_pct, 2),
        imbalance=round(stock.imbalance, 3),
        turnover=stock.turnover,
        score=round(score, 3),
        bias=bias,
        reasons=reasons,
    )


def _book(stock: PreOpenStock) -> str:
    side = "buyers" if stock.imbalance > 0 else "sellers"
    return f"{abs(stock.imbalance) * 100:.0f}% net {side} left in the book"


def build_screens(snapshot: PreOpenSnapshot) -> list[Screen]:
    liquid = [s for s in snapshot.stocks if s.iep > 0 and s.turnover > 0]
    if not liquid:
        return []
    median_turnover = sorted(s.turnover for s in liquid)[len(liquid) // 2]

    def top(candidates: list[Pick]) -> list[Pick]:
        return sorted(candidates, key=lambda p: p.score, reverse=True)[:PICKS_PER_SCREEN]

    momentum_up = [
        _pick(
            s,
            score=s.change_pct * (1 + s.imbalance) * _liquidity(s),
            bias="long",
            reasons=[f"Gap up {s.change_pct:+.2f}%", _book(s)]
            + (["Above-median pre-open turnover"] if s.turnover >= median_turnover else []),
        )
        for s in liquid
        if s.change_pct >= MIN_GAP_PCT and s.imbalance >= MIN_IMBALANCE
    ]
    momentum_down = [
        _pick(
            s,
            score=-s.change_pct * (1 - s.imbalance) * _liquidity(s),
            bias="short",
            reasons=[f"Gap down {s.change_pct:+.2f}%", _book(s)]
            + (["Above-median pre-open turnover"] if s.turnover >= median_turnover else []),
        )
        for s in liquid
        if s.change_pct <= -MIN_GAP_PCT and s.imbalance <= -MIN_IMBALANCE
    ]
    reversals = [
        _pick(
            s,
            score=abs(s.change_pct) * abs(s.imbalance) * _liquidity(s),
            bias="watch",
            reasons=[
                f"Gap {s.change_pct:+.2f}% but {_book(s)}",
                "Order book leans against the gap: watch for a fade",
            ],
        )
        for s in liquid
        if abs(s.change_pct) >= MIN_GAP_PCT
        and abs(s.imbalance) >= MIN_IMBALANCE
        and (s.change_pct > 0) != (s.imbalance > 0)
    ]
    breakouts = [
        _pick(
            s,
            score=s.change_pct * _liquidity(s) + (1 if s.imbalance > 0 else 0),
            bias="long",
            reasons=[
                f"Opening within {(1 - s.iep / float(s.year_high or s.iep)) * 100:.1f}% "
                "of its 52-week high",
                f"Gap {s.change_pct:+.2f}%",
                _book(s),
            ],
        )
        for s in liquid
        if s.near_year_high and s.change_pct > 0
    ]

    return [
        Screen(
            key="momentum_up",
            title="Gap-up momentum",
            description="Opening higher with buyers still in control of the book.",
            picks=top(momentum_up),
        ),
        Screen(
            key="momentum_down",
            title="Gap-down weakness",
            description="Opening lower with sellers still in control of the book.",
            picks=top(momentum_down),
        ),
        Screen(
            key="reversal",
            title="Possible reversals",
            description="The gap and the order book disagree - candidates to fade.",
            picks=top(reversals),
        ),
        Screen(
            key="breakout",
            title="52-week breakout watch",
            description="Opening at or near a one-year high.",
            picks=top(breakouts),
        ),
    ]
