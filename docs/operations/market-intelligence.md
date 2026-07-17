# Market intelligence (AI-CIO)

A read-only, **advisory** market-intelligence layer over the AI-CIO research
pipeline. It tells the rest of the platform what the market regime is, which
tickers rank well today and why, and what the news / options / institutional-flow
reads look like — so the console can display it and strategies can (eventually)
factor it in. It **does not trade**.

> **Hard boundary.** AI-CIO is read-only and advisory. Nothing in this capability
> places an order, modifies a position, or writes to AI-CIO's store. The platform
> opens the AI-CIO DuckDB `read_only=True`, the strategy gate is **log-only**, and
> the pipeline that produces the data runs as an isolated service. If any of that
> starts placing orders, it is a bug — the boundary is the point.

## What AI-CIO provides

AI-CIO (vendored at `ai_cio_phase1/`) is a local-first pipeline over a ~176-stock
NSE F&O universe that writes one DuckDB file:

- `regime` — one row per run: a 9-label regime (`trending_{low,normal,high}`,
  `ranging_{low,normal,high}`, `risk_on`, `risk_off`, `recovery_transition`) plus
  HMM/GMM/ADX/correlation/breadth diagnostics.
- `rankings` — one row per ticker per run: `rank`, `composite_score`, `regime`,
  and the raw weighted dimensions (`rs_60d`, `mom_20d`, `turnover_20d_avg`,
  `atr_pct`, `hv_ratio_10_60`, `oi_score`, `if_score`).
- `news` — deduped headlines with a lexicon sentiment label.
- `options_features` — PCR, max pain, IV skew per ticker.
- `institutional_flow` — bulk/block-deal bias score per ticker.

Regime comes from an HMM + GMM + PELT-changepoint ensemble plus cross-sectional
correlation/breadth, and `config.REGIME_WEIGHTS` re-weights the ranking per regime
— so the regime changes *what "good" looks like*, not just a label.

## Architecture

`modules/market_intel` follows the platform's Clean Architecture, and mirrors the
lightweight read-only `instruments` market-info feature:

- **Domain** (`domain/regime.py`) — framework-free value objects (`Regime`,
  `RankingRow`, `NewsItem`, `OptionsSnapshot`, `InstitutionalBias`), a
  `StrategyFamily` enum, and the pure `is_favourable(regime, family)` rule (a
  regime→family table derived from AI-CIO's `REGIME_WEIGHTS` intent). Fail-open:
  an unknown family or regime label returns "favourable", because this is advice.
- **Infrastructure** (`infrastructure/duckdb_reader.py`) — `AicioDuckDBReader`
  opens the file `read_only=True` with short-lived connections and **degrades to
  empty/None** (never raises) when the file is unconfigured, missing, locked by an
  in-flight pipeline write, or malformed. All SQL is static and value-parameterised.
- **Application** (`application/client.py`, `application/shadow_gate.py`) —
  `AicioClient` is the single facade other code uses (`current_regime`,
  `rankings`, `is_favorable_regime`, `recent_news`, `options_snapshot`,
  `institutional_bias`), wrapping the sync reader in `asyncio.to_thread`.
  `ShadowGate` logs what AI-CIO would advise at each strategy-run start.
- **Presentation** (`presentation/router.py`) — `GET /api/v1/market-intel/{status,
  regime,rankings,news,options/{ticker},flow/{ticker}}`, gated on `ANALYTICS_VIEW`.

The console **Market Intel** page (`/app/market-intel`) shows the regime with
confidence/diagnostics, the top-N ranked opportunities with a per-dimension
breakdown, a selected-ticker detail (options + flow), and recent news.

## Configuration

```
AICIO_DUCKDB_PATH=            # path to AI-CIO's aicio.duckdb; unset => dormant
AICIO_SHADOW_GATE_ENABLED=true
```

Unset `AICIO_DUCKDB_PATH` leaves the feature dormant: the API returns empty/null
and the engine gate is off — the platform runs exactly as before. Under Docker
Compose the path is set to the shared-volume location automatically.

## The pipeline service

`docker-compose` runs `aicio-pipeline` (image `deploy/docker/aicio.Dockerfile`) as
the **sole writer** of the shared `aicio_data` volume; `api` and `trading-engine`
mount it `read_only`. It is **synthetic by default** (`AICIO_DATA_SOURCE=synthetic`),
so bring-up is hermetic and needs no network, and refreshes every
`AICIO_REFRESH_SECONDS` (default daily).

Run order is `run_pipeline → run_market_intel → run_news`: the pipeline writes the
OHLCV that the options module needs for spot prices, so it goes first; the options
`oi_score` dimension folds into the *next* cycle's ranking (a one-cycle lag by
design). To run it by hand:

```bash
cd ai_cio_phase1/ai_cio_phase1
pip install -r requirements.txt
AICIO_DB_PATH=/path/to/aicio.duckdb python run_pipeline.py
AICIO_DB_PATH=/path/to/aicio.duckdb python run_market_intel.py
AICIO_DB_PATH=/path/to/aicio.duckdb python run_news.py
```

## Shadow mode, and the road to live

The strategy gate is **log-only** in this phase. At each run start the trading
engine emits, without changing execution:

- `shadow_gate.regime_opinion` — `would_suspend` for the strategy's family in the
  current regime;
- `shadow_gate.ranking_opinion` — `symbol_ranks` and `would_exclude` for the run's
  instruments (a symbol absent from today's ranking failed AI-CIO's quality gate).

Turning these opinions into real behaviour (actually suspending a strategy or
skipping a ticker) is a **separate, later change**. The source blueprint is
explicit that nothing is trusted in production without **30+ days of shadow
validation**, and that standard carries over: leave `AICIO_SHADOW_GATE_ENABLED=true`
to accumulate the log signal a live rollout would be reviewed against.

## First-run caveats (verify, don't assume)

AI-CIO was built in a sandbox with no outbound network, so:

- **Live data sources** (yfinance, Kite, Google News, Finnhub, NSE options/deals)
  are real code but have never run against live endpoints. Keep the synthetic
  default until you have verified each real source with a small `--limit` run.
- **Symbol mapping**: the shadow gate matches the platform's instrument `symbol`
  to AI-CIO's ticker as a direct NSE-symbol match (e.g. `RELIANCE`). Verify on the
  first real run.
- **DuckDB is single-writer / multi-reader**: readers degrade gracefully on lock
  contention, but the pipeline should be the only writer of the file.
