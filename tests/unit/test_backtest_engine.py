"""Unit tests for the backtesting engine (Phase 12, slice A)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from algo_platform.modules.strategies.domain.backtest import (
    BacktestConfig,
    Bar,
    grid_search,
    monte_carlo,
    run_backtest,
    walk_forward,
)


def _bars(prices: Sequence[float]) -> list[Bar]:
    return [Bar(open=p, high=p, low=p, close=p, volume=1.0) for p in prices]


def _sma_signal(fast: int, slow: int):
    def signal(history: Sequence[Bar]) -> int:
        if len(history) < slow:
            return 0
        closes = [b.close for b in history]
        fast_ma = sum(closes[-fast:]) / fast
        slow_ma = sum(closes[-slow:]) / slow
        return 1 if fast_ma > slow_ma else 0

    return signal


def test_flat_signal_preserves_capital() -> None:
    result = run_backtest(_bars([100, 101, 102, 103]), lambda _h: 0)
    assert result.trades == 0
    assert result.ending_equity == 100_000.0
    assert result.total_return_pct == 0.0


def test_long_in_uptrend_makes_money() -> None:
    bars = _bars([100, 110, 120, 130, 140])
    result = run_backtest(bars, lambda _h: 1, BacktestConfig(fee_bps=0, slippage_bps=0))
    assert result.total_return_pct > 0
    assert result.ending_equity > 100_000.0


def test_fees_reduce_returns() -> None:
    bars = _bars([100, 110, 120])
    no_fee = run_backtest(bars, lambda _h: 1, BacktestConfig(fee_bps=0, slippage_bps=0))
    with_fee = run_backtest(bars, lambda _h: 1, BacktestConfig(fee_bps=50, slippage_bps=50))
    assert with_fee.total_return_pct < no_fee.total_return_pct


def test_result_reports_metrics_and_trades() -> None:
    prices = [100, 102, 101, 105, 107, 106, 110, 112, 111, 115]
    result = run_backtest(_bars(prices), _sma_signal(2, 4))
    assert len(result.equity_curve) == len(prices)
    assert result.trades >= 0
    assert result.max_drawdown_pct >= 0.0
    assert result.ending_equity > 0.0


def test_monte_carlo_percentiles_are_ordered() -> None:
    returns = [0.01, -0.005, 0.008, -0.002, 0.006, -0.004]
    mc = monte_carlo(returns, iterations=500, seed=42)
    assert mc.iterations == 500
    assert mc.p5_return_pct <= mc.p50_return_pct <= mc.p95_return_pct
    assert mc.worst_drawdown_pct >= 0


def test_monte_carlo_is_deterministic_with_seed() -> None:
    returns = [0.01, -0.01, 0.02, -0.015]
    a = monte_carlo(returns, iterations=200, seed=7)
    b = monte_carlo(returns, iterations=200, seed=7)
    assert a == b


def _build(params: Mapping[str, float]):
    return _sma_signal(int(params["fast"]), int(params["slow"]))


def test_grid_search_ranks_by_objective() -> None:
    bars = _bars([100, 101, 103, 102, 105, 108, 107, 110, 113, 112, 116, 119])
    ranked = grid_search(
        bars,
        {"fast": [2, 3], "slow": [4, 6]},
        _build,
        objective=lambda r: r.total_return_pct,
    )
    assert len(ranked) == 4
    # Sorted best-first.
    assert ranked[0].score >= ranked[-1].score


def test_walk_forward_produces_out_of_sample_folds() -> None:
    prices = [100 + i + (5 if i % 4 == 0 else 0) for i in range(48)]
    report = walk_forward(
        _bars(prices),
        {"fast": [2, 3], "slow": [5, 8]},
        _build,
        objective=lambda r: r.total_return_pct,
        folds=3,
    )
    assert len(report.folds) >= 1
    assert isinstance(report.average_oos_return_pct, float)


def test_walk_forward_insufficient_data_is_empty() -> None:
    report = walk_forward(_bars([100, 101]), {"fast": [2]}, _build, objective=lambda r: r.sharpe)
    assert report.folds == []
