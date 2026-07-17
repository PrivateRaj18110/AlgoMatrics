# AI-CIO Phase 1 (right-sized)

A working local version of Phase 1 from the AI-CIO blueprint, scoped to
what a laptop and free daily data can actually support for a 176-stock
NSE universe. No Kafka, no Kubernetes, no ClickHouse -- those earn their
keep at the doc's Enterprise tier (25,000+ instruments), not here.

## Quick start

```
pip install -r requirements.txt
python run_pipeline.py           # normal run
python run_pipeline.py --demo    # also injects one bad ticker to prove the quality gate works
```

Runs out of the box on synthetic data (`config.DATA_SOURCE = "synthetic"`).
Output lands in `output/rankings_<date>.csv` and in `aicio.duckdb`.

## Switching to real data

Set `DATA_SOURCE = "yfinance"` in `config.py` and run somewhere with
internet access to Yahoo Finance (this sandbox has none). Nothing else
changes -- `ingest.py`, `storage.py`, `features.py` etc. don't know or
care whether the data behind them is synthetic or real.

`ingest.py` also has: `get_ohlcv_yfinance_batch()` (one batched request
for the whole universe via `yf.download()`, instead of 176 sequential
ones -- much less likely to get rate-limited), a `with_retry()`
wrapper (exponential backoff, unit-tested in isolation, wraps every real
source), and incremental-fetch support wired into `run_pipeline.py` --
on any run after the first, only bars since the last stored date get
fetched and merged in (`storage.merge_ohlcv`), not the full history
every time. For a broker feed instead, `broker_kite.py` has a real Kite
Connect adapter (the login flow is interactive by design -- Kite's OAuth
step can't be automated headlessly, and scripting around it would
violate their terms).

## File map

| File | What it does | Maps to doc |
|---|---|---|
| `universe.py` | Loads the tradeable universe (176 F&O stocks by default) | M02 (universe definition) |
| `ingest.py` | Synthetic / yfinance (single + batch) / retry-wrapped adapters | M02/M03 data feeds |
| `broker_kite.py` | Zerodha Kite Connect adapter (needs a paid key + interactive login) | Part 3.1 broker APIs |
| `storage.py` | DuckDB schema, upserts, incremental-merge helper | "ClickHouse + Postgres + Redis" |
| `quality.py` | Hard gate (excludes) + soft flags (logs only) | Part 19 data quality risk |
| `features.py` | ~41 features from price/volume/volatility | Part 22 (300+ feature universe) |
| `regime.py` | HMM + GMM + PELT changepoint ensemble + cross-sectional correlation/breadth | M17 / Part 7 |
| `rank.py` | Regime-adjusted composite score, degrades gracefully if a dimension is missing | M25 / Part 8 |
| `run_pipeline.py` | Orchestrates universe -> ingest -> quality -> features -> regime -> rank | -- |
| `news_ingest.py` | 3 news sources, MinHash dedup, lexicon sentiment | M18 / M20 |
| `run_news.py` | News CLI entrypoint | -- |
| `options_ingest.py` | NSE option chain adapter + PCR/max pain/IV skew math | M08 |
| `institutional_flow.py` | NSE bulk/block deal adapter + bias aggregation | M22 |
| `run_market_intel.py` | Options + institutional flow CLI entrypoint | -- |

## Regime engine (HMM + GMM + changepoint + cross-sectional)

A real ensemble, matching the doc's Part 7 architecture, not a rule-based
placeholder:

- **HMM** (3-state `hmmlearn.GaussianHMM` on index log returns) -- the
  primary vol detector, fit with multiple random restarts and filtered
  against degenerate solutions. Verified empirically while building
  this: some random seeds converge to a state with 30x the volatility of
  the others at an *equal or higher* likelihood than a properly-separated
  fit -- picking by raw log-likelihood alone is unsafe.
- **GMM** (3-component, clustered on rolling mean/vol pairs, not returns
  directly) -- a genuinely complementary secondary detector.
- **PELT changepoint detection** (`ruptures`) on rolling realised vol --
  this phase's stand-in for the doc's BOCPD.
- **Cross-sectional average pairwise correlation + breadth** across all
  176 tickers, via an O(N) analytical shortcut instead of an O(N²) full
  pairwise-correlation matrix. This needed the full universe to exist
  first, which is why it wasn't in v0.1.

9 labels come out (`trending_{low,normal,high}`, `ranging_{low,normal,high}`,
`risk_on`, `risk_off`, `recovery_transition`) -- not a literal
reproduction of the doc's R1-R8 (that embeds trading judgment on top of
statistics), but the same conceptual ground. The low-confidence
"transition" trigger is self-calibrated per fit (bottom quartile of that
model's own confidence distribution), not a fixed number -- a threshold
tuned against one HMM fit doesn't transfer cleanly to another.

**Regime now actually changes the ranking**: `config.REGIME_WEIGHTS`
holds a full weight table per regime (inspired by the doc's Part 8.2), so
a `ranging_low` day genuinely ranks stocks differently than a `risk_off`
day -- a regime label nothing downstream reacts to is just a string.

## Options + institutional flow

Same shape as news: the feature *math* is solid and tested against
known-answer cases (force all OI onto one strike -> max pain must land
exactly there; force one-sided bulk buying -> bias score must hit the
correct value). The *live fetch* is the fragile part -- both hit NSE's
own site (`option-chain-equities`, `snapshot-capital-market-largedeal`),
gated by session cookies, liable to change without notice. Confirmed to
exist as of this build; verify against nseindia.com if either breaks. A
broker's option chain (Kite Connect has one) is a real documented API
instead of a scraped one, if this needs to be production-reliable.

```
python run_market_intel.py                          # synthetic, offline
python run_market_intel.py --source real --limit 10  # real NSE fetch, first 10 only
```

Institutional flow is genuinely sparse -- most of the 176 stocks won't
have a bulk/block deal on any given day. `rank.py` handles this: a ticker
with no deal gets a neutral 0 on that dimension rather than being
excluded from the ranking or breaking it.

## What's built vs still deferred

**Built:**
- Universe management, OHLCV ingestion (synthetic/yfinance/Kite, batched, incremental, retrying), quality gate, ~41 features
- Real regime ensemble (HMM + GMM + changepoint + cross-sectional correlation/breadth), regime-adjusted ranking
- News: 3 sources, real MinHash dedup, lexicon sentiment
- Options: PCR, max pain, IV skew, tested against known-answer cases
- Institutional flow: bulk/block deal bias, tested against known-answer cases
- All 7 ranking dimensions wired together, degrading gracefully if any module hasn't been run yet

**Still deferred, and why:**
- **Live network calls** (yfinance, Kite, Google News, Finnhub, NSE options/deals) are all real code, verified via offline unit tests and known-answer tests, but untestable end-to-end from this sandbox (no outbound access to any of those domains). Run with `--limit 10` first wherever you do have network access.
- **FinBERT sentiment, transformer regime classifier** -- both need model weights this sandbox can't download (no huggingface.co egress). The lexicon sentiment and HMM/GMM ensemble are honest placeholders, not permanent choices.
- **Kafka / Kubernetes / ClickHouse / Neo4j** -- revisit only when data volume or team size actually demands it.
- **REST API (Part 16)** -- natural next add-on once something needs to consume `rankings` over the network instead of reading the CSV/DuckDB file directly.
- **Dark pool (M23)** -- skipped outright: that's FINRA/US market structure with no real NSE equivalent, nothing honest to build there for this universe.

## News (v0.1 of M18 + M20)

```
python run_news.py                            # synthetic, offline, safe default
python run_news.py --source google --limit 10 # real Google News RSS, first 10 tickers
python run_news.py --source finnhub --api-key XXX --limit 10   # real, needs a free finnhub.io key
```

There is no "all news" -- treat that as a scope trap, not a target. What
this actually does: recent headlines + source + link per ticker, deduped
(exact SHA-256 + real MinHash LSH near-dup detection, scoped per-company),
lightly scored with a lexicon sentiment placeholder (swap in FinBERT via
`transformers` once you have GPU/network for it -- nothing else changes).
It does not fetch or store full article text, both because most sources
don't license that for scraping and because reproducing article bodies
is a copyright problem regardless of source.

Three sources behind `news_ingest.py`, same output shape:
- `synthetic` -- fake headlines for testing dedup/sentiment/storage offline. Source names are deliberately not real outlets, so demo output can never look like real reporting.
- `google` -- free, no key, unofficial (Google could rate-limit or change the endpoint any time). Throttle it.
- `finnhub` -- real API, free tier, needs your own key. Confirmed India coverage; verify the NSE symbol mapping with one test call before looping over all 176.

Always test new sources with `--limit 10` before pointing them at the full universe.

## Not investment advice

This ranks historical statistical properties of price/volume data. It
is a research and screening tool, not a signal to act on, and a good
backtest is not a promise about the future -- same caveat the original
doc states on every page.
