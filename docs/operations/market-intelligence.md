# Market intelligence (AI-CIO)

> **Since 2026-09 the console's AI-CIO is the movers radar** described in the next
> section: a live, graded forecast of which F&O stocks are likely to make a major
> move today. The DuckDB research pipeline documented further down still exists
> (and feeds the log-only shadow gate), but the console shows it only when it is
> connected (`AICIO_DUCKDB_PATH`), under a "Research pipeline" tab.

## AI-CIO movers radar

Code: `modules/market_insights` — `domain/catalysts.py` (filing/headline
classification), `domain/move_model.py` (features, logistic model, grading),
`application/movers.py` (collection, forecasts, grading, learning, backtest).
Console: **Market Intelligence** → Today's movers · Catalysts · Headlines · Track
record · Market read.

**What it predicts.** For every NSE F&O stock, the chance of a *major move* today:
a close at least `max(3%, 2 × the stock's typical daily move)` from the previous
close (typical = median absolute daily move over 20 sessions). Plus a likely
direction and the reasons.

**Inputs (all public):** NSE corporate filings (rule-classified into ~30
categories with an impact weight and direction), the NSE event calendar
(results due today), ex-dates, the F&O ban list, bulk/block deals, open-interest
spurts, the 09:08 pre-open auction (gap and order-book imbalance), daily price
history (Yahoo), and headlines from Economic Times, Mint, Business Standard and
Google News (titles and links only).

**Schedule (scheduler process, IST, weekdays):** filings every ~9 min 06:30–16:00
then every 15 min to 22:30 (high-impact filings on F&O stocks raise an in-app
alert to the platform owner, max 15/day); headlines every 15 min; exchange events
every 30 min 07:30–09:05; the *overnight* forecast from 08:00, the *opening*
forecast right after the pre-open snapshot; grading at 16:15, then the weights
are refitted on every graded session (backtest + live, last 160).

**Backtest.** On first start with no backtest stored, the scheduler replays the
last 60 sessions in the background (~8 minutes: ~90 NSE filing-archive requests,
210 Yahoo price histories), fits on the first 70 % and grades the last 30 %
unseen. First run (2026-09-19): opening forecast top-10 hit rate **27.8 %** vs a
**8.2 %** base rate (3.4× lift), direction right on 91 % of real movers;
overnight forecast 15 % (1.8×). Re-run from the Track record tab (admin) or
`POST /api/v1/admin/markets/movers?job=backtest`.

**Honest limits.** Uses today's F&O list for past sessions (survivorship); the
open price stands in for the auction price in the backtest; news, OI, ban list
and deals have no history, so their weights stay at the prior until live grades
teach them; on broad market-wide days (e.g. 18 Sep 2026: 21 % of stocks moved)
stock-specific signals add little. It never places orders.

**Optional Claude reading.** With `AI_PROVIDER=anthropic` and `ANTHROPIC_API_KEY`
set, Claude (`MARKET_AI_MODEL`, default `claude-sonnet-5`) also reads each new
material filing's subject and summary and its impact/direction is blended with
the rule-based one. Without a key nothing calls out.

**Morning briefing e-mail.** About 09:10 IST each trading day (after the pre-open
auction; by 09:30 with the overnight forecast if the auction data never came), the
scheduler writes a briefing — last session's grade, today's top 10 with direction
and reasons, overnight filings that matter, exchange events, market cues and a
routine log including every background process's heartbeat — and queues it in the
e-mail outbox to the platform owner(s) plus `DAILY_BRIEFING_RECIPIENTS`. It is also
stored (kind `mv_briefing`) and shown under Market Intelligence → Daily briefing
(owner only), so the daily log exists even while `EMAIL_BACKEND=console`. Delivery
needs `EMAIL_BACKEND=smtp` and `SMTP_*`. Turn off with `DAILY_BRIEFING_ENABLED=false`.
`GET/POST /api/v1/admin/markets/briefing[?send=true]` previews or sends it now.

**Admin jobs:** `POST /api/v1/admin/markets/movers?job=filings|events|news|forecast|grade|backtest`.

**Read API:** `GET /api/v1/markets/movers[?date=]`, `/markets/movers/track-record`,
`/markets/catalysts[?date=&min_impact=]`, `/markets/news[?date=&tagged=true]`.
All state is stored in `market_snapshots` (kinds `mv_*`); no migration needed.

## The research pipeline (DuckDB)

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

## Kubernetes

Manifests live in `deploy/k8s/` (apply in numeric order):

- `15-aicio-storage.yaml` — a **ReadWriteMany** PVC (`algo-aicio-data`) for the
  shared DuckDB. RWX is required because the API runs multiple replicas that read
  it alongside the engine; set `storageClassName` to your cluster's RWX class
  (EFS / Azure Files / Filestore / NFS / CephFS). Without RWX, either provision it
  or skip AI-CIO — also remove the `aicio-data` volume blocks from `30-api.yaml`
  and `50-singletons.yaml`, or those pods stay `Pending` waiting for the PVC.
- `55-aicio-pipeline.yaml` — a daily **CronJob** that runs the pipeline once and
  exits (the sole writer). Image `ghcr.io/algo-matrics/aicio:latest` — **CI must
  build and push it** (it is not the backend image). Seed it immediately on first
  deploy: `kubectl -n algo create job aicio-init --from=cronjob/algo-aicio-pipeline`.
- `30-api.yaml` / `50-singletons.yaml` mount the PVC read-only and set
  `AICIO_DUCKDB_PATH`; an empty/absent file degrades to empty, so the platform
  runs fine before the first pipeline run.

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
