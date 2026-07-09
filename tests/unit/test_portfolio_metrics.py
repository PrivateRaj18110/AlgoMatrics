"""Unit tests for portfolio performance metrics (Phase 11, slice A)."""

from __future__ import annotations

from math import isclose

from algo_platform.modules.portfolio.domain.metrics import (
    alpha,
    annualized_return,
    beta,
    calmar_ratio,
    max_drawdown,
    returns_from_equity,
    sharpe_ratio,
    sortino_ratio,
    volatility,
)


def test_empty_and_short_series_are_zero() -> None:
    assert sharpe_ratio([]) == 0.0
    assert sortino_ratio([0.01]) == 0.0
    assert volatility([]) == 0.0
    assert max_drawdown([]) == 0.0
    assert beta([0.01], [0.01]) == 0.0
    assert annualized_return([]) == 0.0


def test_zero_volatility_gives_zero_sharpe() -> None:
    # Constant positive returns -> zero stdev -> guard returns 0.
    assert sharpe_ratio([0.01, 0.01, 0.01, 0.01]) == 0.0


def test_sharpe_positive_for_good_risk_reward() -> None:
    returns = [0.01, -0.002, 0.008, 0.004, -0.001, 0.006]
    assert sharpe_ratio(returns, periods_per_year=252) > 0


def test_sortino_ignores_upside_volatility() -> None:
    # Same mean, but downside is small -> Sortino exceeds Sharpe here.
    returns = [0.02, 0.02, 0.02, -0.005, 0.02, -0.005]
    assert sortino_ratio(returns) > sharpe_ratio(returns)


def test_max_drawdown_peak_to_trough() -> None:
    equity = [100.0, 120.0, 90.0, 110.0, 60.0, 80.0]
    # Peak 120 -> trough 60 == 50% drawdown.
    assert isclose(max_drawdown(equity), 0.5, rel_tol=1e-9)


def test_max_drawdown_monotonic_increase_is_zero() -> None:
    assert max_drawdown([100.0, 110.0, 120.0]) == 0.0


def test_calmar_is_return_over_drawdown() -> None:
    equity = [100.0, 110.0, 105.0, 120.0]
    returns = returns_from_equity(equity)
    dd = max_drawdown(equity)
    expected = annualized_return(returns) / dd
    assert isclose(calmar_ratio(returns, equity), expected, rel_tol=1e-9)


def test_beta_of_identical_series_is_one() -> None:
    series = [0.01, -0.02, 0.03, -0.01, 0.02]
    assert isclose(beta(series, series), 1.0, rel_tol=1e-9)


def test_beta_of_double_amplitude_is_two() -> None:
    bench = [0.01, -0.02, 0.03, -0.01, 0.02]
    port = [2 * x for x in bench]
    assert isclose(beta(port, bench), 2.0, rel_tol=1e-9)


def test_alpha_zero_when_tracking_benchmark() -> None:
    bench = [0.01, -0.02, 0.03, -0.01, 0.02]
    assert isclose(alpha(bench, bench), 0.0, abs_tol=1e-9)


def test_returns_from_equity() -> None:
    assert returns_from_equity([100.0, 110.0, 99.0]) == [0.1, -0.1]


def test_annualized_return_compounds() -> None:
    # +1% for 252 periods annualizes to roughly (1.01^252 - 1).
    daily = [0.01] * 252
    assert isclose(annualized_return(daily), 1.01**252 - 1, rel_tol=1e-9)
