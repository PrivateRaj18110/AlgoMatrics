"""AI-CIO movers model: which F&O stocks are likely to make a major move today.

What it predicts
    A *major move* is a close at least ``max(3%, 2 x the stock's typical day)``
    away from the previous close, where "typical day" is the median absolute
    daily move over the last 20 sessions. So a sleepy large cap needs 3%, a
    volatile mid cap needs twice its own normal swing. On an ordinary day only
    a few percent of the F&O universe clears that bar; the model's job is to put
    those few at the top of the list.

How
    A logistic model over explainable features — the pre-open gap measured in
    the stock's own typical moves, overnight exchange filings and their impact,
    results dates, news flow, open-interest build-up, the F&O ban list, bulk and
    block deals, volatility clustering and proximity to 52-week extremes.
    Weights start from stated priors and are fitted to real outcomes (a
    backtest over past sessions, then every live day it has been scored on)
    with ridge regularisation *toward the priors*, so features the history
    cannot see keep their prior weight instead of collapsing to zero.

    Two stages share the features: *overnight* (before 09:08, no gap known)
    and *opening* (after the pre-open auction). Each has its own weights.

Honesty
    Every forecast carries the reasons behind its probability, and the model is
    graded after the close every day: hit rate of its top picks against the
    base rate, and whether its direction calls were right. It ranks situations;
    it is not investment advice. Pure functions: no I/O.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

MIN_MAJOR_PCT = 3.0
MAJOR_TYPICAL_MULTIPLE = 2.0
TOP_K = 10
#: A typical daily move at least this large is worth calling out as volatility.
VOLATILE_TYPICAL_PCT = 1.5

FEATURES: tuple[str, ...] = (
    "gap_z",
    "gap_abs",
    "imbalance",
    "typical",
    "prev_z",
    "vol_ratio",
    "catalyst",
    "results",
    "news",
    "oi_spurt",
    "ban",
    "deal",
    "extreme",
)
#: Known only once the pre-open auction has run.
OPENING_ONLY = frozenset({"gap_z", "gap_abs", "imbalance"})

FEATURE_LABELS: dict[str, str] = {
    "gap_z": "Pre-open gap vs its usual day",
    "gap_abs": "Size of the pre-open gap",
    "imbalance": "Pre-open order-book imbalance",
    "typical": "How much it usually moves",
    "prev_z": "Size of yesterday's move",
    "vol_ratio": "Volatility expanding (5-day vs 20-day)",
    "catalyst": "Overnight filings (combined impact)",
    "results": "Results filed or due today",
    "news": "Headlines since yesterday's close",
    "oi_spurt": "Open-interest build-up",
    "ban": "In F&O ban period",
    "deal": "Bulk / block deal yesterday",
    "extreme": "Near a 52-week high or low",
}

# Priors in log-odds per unit of each feature — the starting belief before any
# fitting, and the anchor the ridge penalty pulls toward.
PRIOR_WEIGHTS: dict[str, float] = {
    "gap_z": 0.55,
    "gap_abs": 0.25,
    "imbalance": 0.6,
    "typical": 0.12,
    "prev_z": 0.2,
    "vol_ratio": 0.35,
    "catalyst": 1.6,
    "results": 0.9,
    "news": 0.35,
    "oi_spurt": 0.4,
    "ban": 0.5,
    "deal": 0.3,
    "extreme": 0.25,
}
PRIOR_BIAS = {"overnight": -3.1, "opening": -3.4}

STAGES = ("overnight", "opening")


def clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp = math.exp(value)
    return exp / (1.0 + exp)


# --------------------------------------------------------------------------------------
# Price history → features
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HistoryStats:
    typical_move: float  # median |daily move| %, last 20 sessions
    prev_change: float | None  # last session's move %
    vol_ratio: float | None  # stdev 5 / stdev 20 of daily moves
    near_extreme: bool
    last_close: float | None


def daily_returns(closes: Sequence[float]) -> list[float]:
    return [
        (current - previous) / previous * 100 for previous, current in pairwise(closes) if previous
    ]


def history_stats(
    closes: Sequence[float],
    *,
    year_high: float | None = None,
    year_low: float | None = None,
) -> HistoryStats | None:
    """Stats from closes up to (not including) the day being forecast. None if too short."""
    returns = daily_returns(closes)
    if len(returns) < 10:
        return None
    window = returns[-20:]
    typical = statistics.median(abs(r) for r in window)
    typical = max(typical, 0.3)  # a flat stock should not make every wiggle "major"
    recent = returns[-5:]
    vol20 = statistics.pstdev(window)
    vol5 = statistics.pstdev(recent) if len(recent) >= 3 else None
    last = closes[-1]
    high = year_high or max(closes)
    low = year_low or min(closes)
    near = bool(last) and ((high and last >= 0.98 * high) or (low and last <= 1.02 * low))
    return HistoryStats(
        typical_move=round(typical, 3),
        prev_change=round(returns[-1], 3),
        vol_ratio=round(vol5 / vol20, 3) if vol5 is not None and vol20 > 0 else None,
        near_extreme=bool(near),
        last_close=last,
    )


def major_threshold(typical_move: float) -> float:
    return round(max(MIN_MAJOR_PCT, MAJOR_TYPICAL_MULTIPLE * typical_move), 2)


def is_major(change_pct: float, typical_move: float) -> bool:
    return abs(change_pct) >= major_threshold(typical_move)


@dataclass(frozen=True, slots=True)
class StockInputs:
    """Everything the model knows about one stock before the open."""

    symbol: str
    stats: HistoryStats
    gap_pct: float | None = None  # IEP vs previous close, opening stage only
    imbalance: float | None = None  # (buy - sell) / (buy + sell)
    catalyst_impact: float = 0.0  # combined overnight filing impact, 0..1
    results: bool = False
    news_count: int = 0
    oi_change_pct: float | None = None
    in_ban: bool = False
    large_deal: bool = False


def feature_vector(inputs: StockInputs) -> dict[str, float]:
    stats = inputs.stats
    typical = stats.typical_move
    gap = inputs.gap_pct
    return {
        "gap_z": clip(abs(gap) / typical, 0, 6) if gap is not None else 0.0,
        "gap_abs": clip(abs(gap), 0, 8) if gap is not None else 0.0,
        "imbalance": clip(abs(inputs.imbalance), 0, 1) if inputs.imbalance is not None else 0.0,
        "typical": clip(typical, 0, 6),
        "prev_z": clip(abs(stats.prev_change) / typical, 0, 6)
        if stats.prev_change is not None
        else 0.0,
        "vol_ratio": clip(stats.vol_ratio, 0, 4) if stats.vol_ratio is not None else 1.0,
        "catalyst": clip(inputs.catalyst_impact, 0, 1),
        "results": 1.0 if inputs.results else 0.0,
        "news": math.log1p(max(0, inputs.news_count)),
        "oi_spurt": clip((inputs.oi_change_pct or 0.0) / 50, 0, 2),
        "ban": 1.0 if inputs.in_ban else 0.0,
        "deal": 1.0 if inputs.large_deal else 0.0,
        "extreme": 1.0 if stats.near_extreme else 0.0,
    }


def stage_vector(features: Mapping[str, float], stage: str) -> list[float]:
    """Features in FEATURES order; the overnight stage cannot see the auction."""
    return [
        0.0 if stage == "overnight" and name in OPENING_ONLY else float(features.get(name, 0.0))
        for name in FEATURES
    ]


# --------------------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------------------


@dataclass(slots=True)
class StageWeights:
    bias: float
    weights: dict[str, float]

    def logit(self, vector: Sequence[float]) -> float:
        return self.bias + sum(
            self.weights[name] * x for name, x in zip(FEATURES, vector, strict=True)
        )

    def probability(self, vector: Sequence[float]) -> float:
        return sigmoid(self.logit(vector))

    def as_dict(self) -> dict[str, Any]:
        return {
            "bias": round(self.bias, 4),
            "weights": {k: round(v, 4) for k, v in self.weights.items()},
        }

    @staticmethod
    def from_dict(raw: Mapping[str, Any]) -> StageWeights:
        weights = {
            name: float(raw.get("weights", {}).get(name, PRIOR_WEIGHTS[name])) for name in FEATURES
        }
        return StageWeights(bias=float(raw.get("bias", -3.0)), weights=weights)


def prior_model() -> dict[str, StageWeights]:
    return {stage: StageWeights(PRIOR_BIAS[stage], dict(PRIOR_WEIGHTS)) for stage in STAGES}


def fit_logistic(
    rows: Sequence[Sequence[float]],
    labels: Sequence[int],
    *,
    prior: StageWeights,
    ridge: float = 4.0,
    iterations: int = 12,
) -> StageWeights:
    """Newton-Raphson logistic regression, ridge-regularised toward ``prior``.

    The bias is fitted freely; each weight is pulled toward its prior with
    strength ``ridge`` (in units of samples). A feature that never varies in
    the data therefore keeps its prior weight exactly.
    """
    n_features = len(FEATURES)
    size = n_features + 1
    beta = [prior.bias] + [prior.weights[name] for name in FEATURES]
    anchor = list(beta)
    if not rows:
        return StageWeights(prior.bias, dict(prior.weights))
    for _ in range(iterations):
        gradient = [0.0] * size
        hessian = [[0.0] * size for _ in range(size)]
        for vector, label in zip(rows, labels, strict=True):
            x = (1.0, *vector)
            z = sum(b * xi for b, xi in zip(beta, x, strict=True))
            p = sigmoid(z)
            error = p - label
            weight = max(p * (1 - p), 1e-6)
            for i in range(size):
                xi = x[i]
                if xi == 0.0:
                    continue
                gradient[i] += error * xi
                row = hessian[i]
                wxi = weight * xi
                for j in range(i, size):
                    xj = x[j]
                    if xj != 0.0:
                        row[j] += wxi * xj
        for i in range(size):
            for j in range(i):
                hessian[i][j] = hessian[j][i]
        for i in range(1, size):
            gradient[i] += ridge * (beta[i] - anchor[i])
            hessian[i][i] += ridge
        hessian[0][0] += 1e-6
        step = _solve(hessian, gradient)
        if step is None:
            break
        beta = [b - s for b, s in zip(beta, step, strict=True)]
        if max(abs(s) for s in step) < 1e-5:
            break
    return StageWeights(beta[0], dict(zip(FEATURES, beta[1:], strict=True)))


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float] | None:
    """Gaussian elimination with partial pivoting; None when singular."""
    size = len(vector)
    a = [[*row, vector[i]] for i, row in enumerate(matrix)]
    for col in range(size):
        pivot = max(range(col, size), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-12:
            return None
        a[col], a[pivot] = a[pivot], a[col]
        for r in range(col + 1, size):
            factor = a[r][col] / a[col][col]
            if factor:
                for c in range(col, size + 1):
                    a[r][c] -= factor * a[col][c]
    solution = [0.0] * size
    for r in range(size - 1, -1, -1):
        solution[r] = (a[r][size] - sum(a[r][c] * solution[c] for c in range(r + 1, size))) / a[r][
            r
        ]
    return solution


# --------------------------------------------------------------------------------------
# Direction and reasons
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DirectionCall:
    direction: str  # up | down | either
    basis: str
    confidence: str  # high | medium | low


def direction_call(
    *,
    gap_pct: float | None,
    imbalance: float | None,
    catalyst_direction: float,
    news_sentiment: int,
) -> DirectionCall:
    """Which way, if it moves. The pre-open gap dominates once known."""
    if gap_pct is not None and abs(gap_pct) >= 1.0:
        up = gap_pct > 0
        agrees = imbalance is not None and abs(imbalance) >= 0.2 and (imbalance > 0) == up
        return DirectionCall(
            "up" if up else "down",
            "pre-open gap" + (" backed by the order book" if agrees else ""),
            "high" if agrees else "medium",
        )
    lean = catalyst_direction + 0.15 * clip(news_sentiment, -3, 3)
    if lean >= 0.3:
        return DirectionCall("up", "positive filings / news", "medium" if lean >= 0.6 else "low")
    if lean <= -0.3:
        return DirectionCall("down", "negative filings / news", "medium" if lean <= -0.6 else "low")
    return DirectionCall("either", "no directional evidence", "low")


def reasons(
    inputs: StockInputs,
    features: Mapping[str, float],
    model: StageWeights,
    stage: str,
    *,
    catalyst_labels: Sequence[str] = (),
    results_label: str | None = None,
) -> list[dict[str, Any]]:
    """Human-readable drivers, largest contribution first."""
    vector = stage_vector(features, stage)
    contributions = {
        name: model.weights[name] * x for name, x in zip(FEATURES, vector, strict=True)
    }
    stats = inputs.stats
    text: dict[str, str] = {}
    if inputs.gap_pct is not None and stage == "opening":
        text["gap_z"] = (
            f"Pre-open gap {inputs.gap_pct:+.1f}% — {features['gap_z']:.1f}x its usual day"
        )
        text["gap_abs"] = text["gap_z"]
    if inputs.imbalance is not None and stage == "opening":
        side = "buy" if inputs.imbalance > 0 else "sell"
        share = f"{abs(inputs.imbalance) * 100:.0f}%"
        against = (
            inputs.gap_pct is not None
            and abs(inputs.gap_pct) >= 0.5
            and ((inputs.imbalance > 0) != (inputs.gap_pct > 0))
        )
        text["imbalance"] = (
            f"Order book {side}-heavy against the gap ({share}) - reversal risk"
            if against
            else f"Order book {side}-heavy ({share} imbalance)"
        )
    # Only worth saying when the stock really is lively; a calm stock's level is
    # a small contribution, not a reason.
    if stats.typical_move >= VOLATILE_TYPICAL_PCT:
        text["typical"] = f"Volatile stock: usually moves about {stats.typical_move:.1f}% a day"
    if stats.prev_change is not None:
        text["prev_z"] = (
            f"Moved {stats.prev_change:+.1f}% last session ({features['prev_z']:.1f}x usual)"
        )
    if stats.vol_ratio is not None:
        text["vol_ratio"] = (
            f"Volatility expanding: 5-day swings {stats.vol_ratio:.1f}x the 20-day norm"
        )
    if catalyst_labels:
        text["catalyst"] = "Filings: " + ", ".join(dict.fromkeys(catalyst_labels))
    if inputs.results:
        text["results"] = results_label or "Results filed overnight or due today"
    if inputs.news_count:
        plural = "s" if inputs.news_count != 1 else ""
        text["news"] = f"{inputs.news_count} headline{plural} since yesterday's close"
    if inputs.oi_change_pct:
        text["oi_spurt"] = f"Open interest up {inputs.oi_change_pct:.0f}% last session"
    if inputs.in_ban:
        text["ban"] = "In F&O ban period — positions can only be reduced"
    if inputs.large_deal:
        text["deal"] = "Bulk / block deal last session"
    if stats.near_extreme:
        text["extreme"] = "Trading near its 52-week high or low"

    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for name, value in sorted(contributions.items(), key=lambda item: -item[1]):
        if value < 0.12 or name not in text or text[name] in seen:
            continue
        seen.add(text[name])
        out.append({"feature": name, "text": text[name], "weight": round(value, 2)})
    return out[:5]


# --------------------------------------------------------------------------------------
# Grading
# --------------------------------------------------------------------------------------


@dataclass(slots=True)
class DayGrade:
    top_k: int
    hits: int
    majors: int
    universe: int
    direction_calls: int
    direction_right: int
    brier: float | None
    hit_symbols: list[str] = field(default_factory=list)
    missed_symbols: list[str] = field(default_factory=list)

    @property
    def precision(self) -> float | None:
        return self.hits / self.top_k if self.top_k else None

    @property
    def base_rate(self) -> float | None:
        return self.majors / self.universe if self.universe else None

    @property
    def recall(self) -> float | None:
        return self.hits / self.majors if self.majors else None

    @property
    def lift(self) -> float | None:
        base = self.base_rate
        precision = self.precision
        return precision / base if base and precision is not None else None

    def as_dict(self) -> dict[str, Any]:
        def r(value: float | None, digits: int = 4) -> float | None:
            return None if value is None else round(value, digits)

        return {
            "top_k": self.top_k,
            "hits": self.hits,
            "majors": self.majors,
            "universe": self.universe,
            "precision": r(self.precision),
            "base_rate": r(self.base_rate),
            "recall": r(self.recall),
            "lift": r(self.lift, 2),
            "direction_calls": self.direction_calls,
            "direction_right": self.direction_right,
            "brier": r(self.brier),
            "hit_symbols": self.hit_symbols,
            "missed_symbols": self.missed_symbols[:15],
        }


def grade_day(
    predictions: Sequence[tuple[str, float, str]],
    outcomes: Mapping[str, tuple[bool, float]],
    *,
    top_k: int = TOP_K,
) -> DayGrade:
    """``predictions``: (symbol, probability, direction) ranked or not.
    ``outcomes``: symbol → (was it a major move, % change close to close)."""
    scored = [(s, p, d) for s, p, d in predictions if s in outcomes]
    scored.sort(key=lambda item: -item[1])
    top = scored[:top_k]
    hits = [s for s, _, _ in top if outcomes[s][0]]
    majors = [s for s in outcomes if outcomes[s][0]]
    calls = right = 0
    for symbol, _, direction in top:
        major, change = outcomes[symbol]
        if major and direction in ("up", "down"):
            calls += 1
            right += int((change > 0) == (direction == "up"))
    brier = (
        sum((p - (1.0 if outcomes[s][0] else 0.0)) ** 2 for s, p, _ in scored) / len(scored)
        if scored
        else None
    )
    top_symbols = {s for s, _, _ in top}
    return DayGrade(
        top_k=len(top),
        hits=len(hits),
        majors=len(majors),
        universe=len(outcomes),
        direction_calls=calls,
        direction_right=right,
        brier=brier,
        hit_symbols=hits,
        missed_symbols=sorted(
            (s for s in majors if s not in top_symbols), key=lambda s: -abs(outcomes[s][1])
        ),
    )


def summarise(grades: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Pool daily grades (``DayGrade.as_dict()`` form): totals, not averages of ratios."""
    top = sum(int(g.get("top_k") or 0) for g in grades)
    hits = sum(int(g.get("hits") or 0) for g in grades)
    majors = sum(int(g.get("majors") or 0) for g in grades)
    universe = sum(int(g.get("universe") or 0) for g in grades)
    calls = sum(int(g.get("direction_calls") or 0) for g in grades)
    right = sum(int(g.get("direction_right") or 0) for g in grades)
    briers = [float(g["brier"]) for g in grades if g.get("brier") is not None]
    precision = hits / top if top else None
    base = majors / universe if universe else None
    return {
        "days": len(grades),
        "top_k_picks": top,
        "hits": hits,
        "precision": round(precision, 4) if precision is not None else None,
        "base_rate": round(base, 4) if base is not None else None,
        "lift": round(precision / base, 2) if precision is not None and base else None,
        "recall": round(hits / majors, 4) if majors else None,
        "direction_accuracy": round(right / calls, 4) if calls else None,
        "direction_calls": calls,
        "brier": round(sum(briers) / len(briers), 5) if briers else None,
    }


def calibration(
    pairs: Sequence[tuple[float, bool]], buckets: Sequence[float] = (0.05, 0.1, 0.2, 0.35, 0.5, 1.0)
) -> list[dict[str, Any]]:
    """Predicted probability bands vs how often a major move actually happened."""
    out: list[dict[str, Any]] = []
    low = 0.0
    for high in buckets:
        members = [(p, y) for p, y in pairs if low <= p < high or (high == 1.0 and p == 1.0)]
        if members:
            out.append(
                {
                    "band": f"{low * 100:.0f}-{high * 100:.0f}%",
                    "count": len(members),
                    "predicted": round(sum(p for p, _ in members) / len(members), 4),
                    "actual": round(sum(1 for _, y in members if y) / len(members), 4),
                }
            )
        low = high
    return out
