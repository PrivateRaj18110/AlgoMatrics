# Backtesting engine (Phase 12)

A deterministic engine that replays a bar series through a strategy, simulates
fills, and scores the result with the shared portfolio metrics. Includes Monte
Carlo simulation, parameter-search optimization, and walk-forward evaluation.

## Engine (`strategies/domain/backtest.py`, pure)

- **`run_backtest(bars, signal, config)`** — bar replay: at each bar the signal
  function returns a target position (`-1/0/+1`); fills apply `fee_bps` +
  `slippage_bps`; the result carries the equity curve, trades, win rate, and
  Sharpe/Sortino/Calmar/max-drawdown/annualized return.
- **`monte_carlo(returns, iterations, seed)`** — seeded bootstrap resampling of
  the strategy's period returns into a distribution (p5/p50/p95 return, worst
  drawdown). Deterministic per seed.
- **`grid_search(bars, grid, build_signal, objective)`** — runs the engine for
  every parameter combination, ranked best-first by an objective.
- **`walk_forward(bars, grid, build_signal, objective, folds)`** — optimizes on
  each in-sample window and evaluates on the next out-of-sample window, rolling
  forward; reports the average out-of-sample return.

Tick replay is bar replay at the finest granularity — feed tick-derived bars.

## Strategy types

`strategies/application/backtest_signals.py` provides pure, bar-based signal
builders for `sma_crossover`, `rsi_reversion`, and `breakout` (mirroring the
built-in strategies' candle logic). New types register here to become
backtestable.

## API (`/api/v1/backtests`, permission-gated)

| Method & path | Purpose |
|---|---|
| `GET /signal-types` | Available strategy types |
| `POST /run` | Run and persist a backtest; returns scored metrics |
| `POST /monte-carlo` | Run + Monte Carlo distribution |
| `POST /optimize` | Grid search ranked by `sharpe`/`total_return`/`calmar` |
| `GET /` / `GET /{id}` | List / fetch stored runs |

Runs are stored per organization (`backtest_runs`, migration 0011) with the
params, config, and scored summary.

## Frontend

`/app/backtesting` runs a backtest over an editable price series and shows the
metric tiles. Wiring it to instrument candle history is a straightforward
follow-up (the endpoint accepts a bar array).

## Rollback

Additive: a pure engine, a new table, and a new router. `alembic downgrade 0010`
drops `backtest_runs`. Revert the `phase-12-backtesting` branch to remove it with
no impact elsewhere.
