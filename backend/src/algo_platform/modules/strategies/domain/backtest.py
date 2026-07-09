"""Deterministic backtesting engine (pure, framework-free).

Replays a bar series through a signal function, simulates fills with fees and
slippage, and scores the result with the shared portfolio metrics. Also provides
Monte Carlo return simulation, grid-search optimization, and walk-forward
evaluation. Everything is deterministic given its inputs (Monte Carlo takes an
explicit seed), so runs are reproducible and unit testable.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from itertools import product

from algo_platform.modules.portfolio.domain.metrics import (
    annualized_return,
    calmar_ratio,
    max_drawdown,
    returns_from_equity,
    sharpe_ratio,
    sortino_ratio,
)


@dataclass(frozen=True, slots=True)
class Bar:
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    initial_cash: float = 100_000.0
    fee_bps: float = 2.0  # per trade, on notional
    slippage_bps: float = 1.0
    periods_per_year: int = 252


# A signal function receives the bar history up to and including the current bar
# and returns the desired position: -1 (short), 0 (flat), or +1 (long).
SignalFn = Callable[[Sequence[Bar]], int]


@dataclass(frozen=True, slots=True)
class BacktestResult:
    equity_curve: list[float]
    returns: list[float]
    total_return_pct: float
    max_drawdown_pct: float
    sharpe: float
    sortino: float
    calmar: float
    annualized_return_pct: float
    trades: int
    win_rate_pct: float
    ending_equity: float


def run_backtest(
    bars: Sequence[Bar], signal: SignalFn, config: BacktestConfig | None = None
) -> BacktestResult:
    cfg = config or BacktestConfig()
    cash = cfg.initial_cash
    position = 0  # -1 / 0 / +1
    entry_price = 0.0
    units = 0.0
    equity_curve: list[float] = []
    trade_results: list[float] = []
    cost_rate = (cfg.fee_bps + cfg.slippage_bps) / 10_000.0

    for i in range(len(bars)):
        price = bars[i].close
        target = signal(bars[: i + 1])
        if target != position:
            # Close any existing position at this price.
            if position != 0:
                gross = (price - entry_price) * units * position
                cost = abs(units) * price * cost_rate
                pnl = gross - cost
                cash += pnl
                trade_results.append(pnl)
            # Open the new position (sized to deploy all cash at this price).
            if target != 0 and price > 0:
                units = cash / price
                entry_price = price
                cash -= abs(units) * price * cost_rate  # entry cost
                position = target
            else:
                units = 0.0
                position = 0
        # Mark-to-market equity.
        mark = cash + (price - entry_price) * units * position if position != 0 else cash
        equity_curve.append(mark)

    returns = returns_from_equity(equity_curve)
    ending = equity_curve[-1] if equity_curve else cfg.initial_cash
    wins = sum(1 for pnl in trade_results if pnl > 0)
    win_rate = (wins / len(trade_results) * 100) if trade_results else 0.0
    total_return = (ending / cfg.initial_cash - 1.0) * 100 if cfg.initial_cash else 0.0

    return BacktestResult(
        equity_curve=equity_curve,
        returns=returns,
        total_return_pct=round(total_return, 4),
        max_drawdown_pct=round(max_drawdown(equity_curve) * 100, 4),
        sharpe=round(sharpe_ratio(returns, periods_per_year=cfg.periods_per_year), 4),
        sortino=round(sortino_ratio(returns, periods_per_year=cfg.periods_per_year), 4),
        calmar=round(
            calmar_ratio(returns, equity_curve, periods_per_year=cfg.periods_per_year), 4
        ),
        annualized_return_pct=round(
            annualized_return(returns, periods_per_year=cfg.periods_per_year) * 100, 4
        ),
        trades=len(trade_results),
        win_rate_pct=round(win_rate, 4),
        ending_equity=round(ending, 2),
    )


@dataclass(frozen=True, slots=True)
class MonteCarloResult:
    iterations: int
    p5_return_pct: float
    p50_return_pct: float
    p95_return_pct: float
    worst_drawdown_pct: float


def monte_carlo(
    returns: Sequence[float], *, iterations: int = 1_000, horizon: int | None = None, seed: int = 0
) -> MonteCarloResult:
    """Bootstrap-resample period returns to a distribution of outcomes."""
    if not returns:
        return MonteCarloResult(0, 0.0, 0.0, 0.0, 0.0)
    rng = random.Random(seed)  # noqa: S311 - simulation sampling, not cryptographic
    length = horizon or len(returns)
    finals: list[float] = []
    worst_dd = 0.0
    for _ in range(iterations):
        sample = [rng.choice(returns) for _ in range(length)]
        equity = 1.0
        curve = [equity]
        for r in sample:
            equity *= 1.0 + r
            curve.append(equity)
        finals.append((equity - 1.0) * 100)
        worst_dd = max(worst_dd, max_drawdown(curve))
    finals.sort()

    def pct(p: float) -> float:
        idx = min(len(finals) - 1, max(0, int(p * len(finals))))
        return round(finals[idx], 4)

    return MonteCarloResult(
        iterations=iterations,
        p5_return_pct=pct(0.05),
        p50_return_pct=pct(0.50),
        p95_return_pct=pct(0.95),
        worst_drawdown_pct=round(worst_dd * 100, 4),
    )


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    params: dict[str, float]
    score: float
    result: BacktestResult


# Builds a signal function from a concrete parameter set.
SignalBuilder = Callable[[Mapping[str, float]], SignalFn]
Objective = Callable[[BacktestResult], float]


def _param_combinations(grid: Mapping[str, Sequence[float]]) -> Iterable[dict[str, float]]:
    keys = list(grid)
    for combo in product(*(grid[k] for k in keys)):
        yield dict(zip(keys, combo, strict=True))


def grid_search(
    bars: Sequence[Bar],
    grid: Mapping[str, Sequence[float]],
    build_signal: SignalBuilder,
    *,
    objective: Objective,
    config: BacktestConfig | None = None,
) -> list[OptimizationResult]:
    """Run the engine for every parameter combination, ranked best-first."""
    results: list[OptimizationResult] = []
    for params in _param_combinations(grid):
        result = run_backtest(bars, build_signal(params), config)
        results.append(
            OptimizationResult(params=params, score=objective(result), result=result)
        )
    results.sort(key=lambda r: r.score, reverse=True)
    return results


@dataclass(frozen=True, slots=True)
class WalkForwardFold:
    in_sample_params: dict[str, float]
    out_of_sample: BacktestResult


@dataclass(frozen=True, slots=True)
class WalkForwardReport:
    folds: list[WalkForwardFold] = field(default_factory=list)

    @property
    def average_oos_return_pct(self) -> float:
        if not self.folds:
            return 0.0
        return round(
            sum(f.out_of_sample.total_return_pct for f in self.folds) / len(self.folds), 4
        )


def walk_forward(
    bars: Sequence[Bar],
    grid: Mapping[str, Sequence[float]],
    build_signal: SignalBuilder,
    *,
    objective: Objective,
    folds: int = 3,
    config: BacktestConfig | None = None,
) -> WalkForwardReport:
    """Optimize on each in-sample window, evaluate on the next out-of-sample one."""
    if folds < 1 or len(bars) < folds * 2:
        return WalkForwardReport()
    window = len(bars) // (folds + 1)
    report_folds: list[WalkForwardFold] = []
    for k in range(folds):
        in_start = k * window
        in_end = in_start + window
        out_end = in_end + window
        in_sample = bars[in_start:in_end]
        out_sample = bars[in_end:out_end]
        if len(in_sample) < 2 or len(out_sample) < 2:
            continue
        ranked = grid_search(in_sample, grid, build_signal, objective=objective, config=config)
        best = ranked[0]
        oos = run_backtest(out_sample, build_signal(best.params), config)
        report_folds.append(WalkForwardFold(in_sample_params=best.params, out_of_sample=oos))
    return WalkForwardReport(folds=report_folds)
