# Portfolio analytics (Phase 11)

Risk-adjusted performance metrics on top of the existing portfolio dashboard,
equity curve, drawdown, exposure, and allocation views.

## Metrics library

`modules/portfolio/domain/metrics.py` is pure and unit tested. It operates on a
series of periodic returns (fractions) or equity levels:

| Metric | Meaning |
|---|---|
| `sharpe_ratio` | Annualized excess return per unit of total volatility |
| `sortino_ratio` | Like Sharpe but penalizes only downside volatility |
| `calmar_ratio` | Annualized return divided by max drawdown |
| `max_drawdown` | Largest peak-to-trough decline (fraction) |
| `annualized_return` | Geometric annualized return |
| `volatility` | Annualized standard deviation of returns |
| `alpha` / `beta` | CAPM sensitivity/excess vs a benchmark |

All functions are defensive: too-short or degenerate inputs (e.g. zero
volatility) return `0.0` rather than raising, so a metric is always available.
Annualization uses 252 trading periods per year by default.

## Where they surface

`GET /api/v1/portfolio/performance` (the `PerformanceSummaryResponse`) now
includes `sharpe_ratio`, `sortino_ratio`, `calmar_ratio`, and
`annualized_return_pct`, computed from the account equity curve's periodic
returns (`returns_from_equity`). The Analytics page shows them in the
Performance breakdown alongside win rate, profit factor, drawdown, and exposure.

Exposure and asset/sector allocation continue to be served by the existing
`exposure_breakdown` / allocation endpoints and the live equity/drawdown charts.

## Alpha / beta

`alpha` and `beta` are implemented but require a benchmark return series. Wire a
benchmark price feed (e.g. NIFTY 50) and pass its returns to expose them; until
then the summary omits them.

## Rollback

Additive only — a new pure module plus four response fields. No schema change.
Revert the `phase-11-analytics` branch to remove them; the rest of the portfolio
analytics is unaffected.
