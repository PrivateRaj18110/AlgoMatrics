"""Risk-adjusted performance metrics (pure, framework-free).

Functions operate on a series of periodic returns (fractions, e.g. 0.01 = +1%)
or an equity level series. They are defensive: too-short or degenerate inputs
return 0.0 rather than raising, so callers can surface a metric even for a thin
history. Annualization uses ``periods_per_year`` (252 trading days by default).
"""

from __future__ import annotations

from collections.abc import Sequence
from math import sqrt

_TRADING_DAYS = 252


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _stdev(values: Sequence[float]) -> float:
    """Sample standard deviation; 0.0 for fewer than two points."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = _mean(values)
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return sqrt(variance)


def annualized_return(returns: Sequence[float], *, periods_per_year: int = _TRADING_DAYS) -> float:
    """Geometric annualized return from periodic returns."""
    if not returns:
        return 0.0
    growth = 1.0
    for r in returns:
        growth *= 1.0 + r
    if growth <= 0:
        return -1.0
    return float(growth ** (periods_per_year / len(returns))) - 1.0


def volatility(
    returns: Sequence[float], *, annualized: bool = True, periods_per_year: int = _TRADING_DAYS
) -> float:
    vol = _stdev(returns)
    return vol * sqrt(periods_per_year) if annualized else vol


def sharpe_ratio(
    returns: Sequence[float],
    *,
    risk_free: float = 0.0,
    periods_per_year: int = _TRADING_DAYS,
) -> float:
    """Annualized Sharpe ratio. ``risk_free`` is the per-period risk-free rate."""
    if len(returns) < 2:
        return 0.0
    excess = [r - risk_free for r in returns]
    sd = _stdev(excess)
    if sd == 0:
        return 0.0
    return _mean(excess) / sd * sqrt(periods_per_year)


def sortino_ratio(
    returns: Sequence[float],
    *,
    risk_free: float = 0.0,
    periods_per_year: int = _TRADING_DAYS,
) -> float:
    """Annualized Sortino ratio (downside deviation in the denominator)."""
    if len(returns) < 2:
        return 0.0
    excess = [r - risk_free for r in returns]
    downside = [min(0.0, e) for e in excess]
    downside_dev = sqrt(sum(d**2 for d in downside) / len(excess))
    if downside_dev == 0:
        return 0.0
    return _mean(excess) / downside_dev * sqrt(periods_per_year)


def max_drawdown(equity: Sequence[float]) -> float:
    """Largest peak-to-trough decline as a positive fraction (0.2 == -20%)."""
    peak = float("-inf")
    worst = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            worst = max(worst, (peak - value) / peak)
    return worst


def calmar_ratio(
    returns: Sequence[float],
    equity: Sequence[float],
    *,
    periods_per_year: int = _TRADING_DAYS,
) -> float:
    """Annualized return divided by the maximum drawdown."""
    dd = max_drawdown(equity)
    if dd == 0:
        return 0.0
    return annualized_return(returns, periods_per_year=periods_per_year) / dd


def beta(returns: Sequence[float], benchmark: Sequence[float]) -> float:
    """Sensitivity of the portfolio to the benchmark (cov / benchmark variance)."""
    n = min(len(returns), len(benchmark))
    if n < 2:
        return 0.0
    r = returns[-n:]
    b = benchmark[-n:]
    r_mean, b_mean = _mean(r), _mean(b)
    covariance = sum((r[i] - r_mean) * (b[i] - b_mean) for i in range(n)) / (n - 1)
    b_variance = sum((x - b_mean) ** 2 for x in b) / (n - 1)
    if b_variance == 0:
        return 0.0
    return covariance / b_variance


def alpha(
    returns: Sequence[float],
    benchmark: Sequence[float],
    *,
    risk_free: float = 0.0,
    periods_per_year: int = _TRADING_DAYS,
) -> float:
    """Annualized Jensen's alpha versus the benchmark (CAPM)."""
    n = min(len(returns), len(benchmark))
    if n < 2:
        return 0.0
    b = beta(returns, benchmark)
    port = annualized_return(returns[-n:], periods_per_year=periods_per_year)
    bench = annualized_return(benchmark[-n:], periods_per_year=periods_per_year)
    rf_annual = risk_free * periods_per_year
    return port - (rf_annual + b * (bench - rf_annual))


def returns_from_equity(equity: Sequence[float]) -> list[float]:
    """Convert an equity level series into periodic simple returns."""
    out: list[float] = []
    for i in range(1, len(equity)):
        prev = equity[i - 1]
        if prev > 0:
            out.append((equity[i] - prev) / prev)
    return out
