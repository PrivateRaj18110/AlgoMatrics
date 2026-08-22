"""
Run the whole Phase 1 pipeline end to end:
  universe -> ingest -> quality gate -> features -> regime -> rank -> output/rankings_<date>.csv

    python run_pipeline.py            # normal run
    python run_pipeline.py --demo     # also injects a bad ticker to prove the quality gate works
"""
import sys
import numpy as np
import pandas as pd

import config
import universe as uv
import ingest
import storage
import quality
import features as feat
import regime as rg
import rank


def main(demo: bool = False):
    config.OUTPUT_DIR.mkdir(exist_ok=True)
    run_date = pd.Timestamp.today().normalize().date()

    uni = uv.load_universe()
    print(f"Universe: {len(uni)} tickers from {config.UNIVERSE_CSV.name}")

    index_df = ingest.get_index_ohlcv()
    index_log_ret = np.log(index_df["close"]).diff().fillna(0).values
    print(f"Index rows: {len(index_df)}")

    store = storage.Store()
    rng = np.random.default_rng(7)
    demo_bad_ticker = uni["ticker"].sample(1, random_state=1).iloc[0] if demo else None

    all_quality_results = {}
    latest_rows = []
    excluded = []
    close_by_ticker = {}  # accumulated for the cross-sectional regime engine

    for _, row in uni.iterrows():
        ticker = row["ticker"]
        try:
            if config.DATA_SOURCE == "synthetic":
                df = ingest.get_ohlcv(ticker, index_returns=index_log_ret)
            else:
                # Incremental: only fetch what's missing since the last
                # stored bar, then merge -- avoids re-pulling 750 days
                # of unchanged history on every daily run against a real
                # rate-limited source.
                last_date = store.latest_date(ticker)
                if last_date is None:
                    df = ingest.get_ohlcv(ticker)
                else:
                    days_needed = (pd.Timestamp.today().normalize() - pd.Timestamp(last_date)).days + 5
                    new_bars = ingest.get_ohlcv(ticker, n_days=min(days_needed, config.HISTORY_TRADING_DAYS))
                    df = storage.merge_ohlcv(store.read_ohlcv(ticker), new_bars, max_days=config.HISTORY_TRADING_DAYS)
        except Exception as e:
            all_quality_results[ticker] = [{"check_name": "fetch", "passed": False,
                                             "severity": "hard", "detail": str(e), "ticker": ticker}]
            excluded.append((ticker, f"fetch failed: {e}"))
            continue

        if demo and ticker == demo_bad_ticker:
            df = ingest.inject_demo_quality_issues(df, rng)

        checks = quality.run_quality_checks(df, ticker)
        all_quality_results[ticker] = checks
        store.save_ohlcv(df, ticker)

        if not quality.passes_hard_gate(checks):
            failed = [c["check_name"] for c in checks if c["severity"] == "hard" and not c["passed"]]
            excluded.append((ticker, f"failed hard gate: {', '.join(failed)}"))
            continue

        close_by_ticker[ticker] = df.set_index("date")["close"]

        f = feat.compute_features(df, index_df)
        long = f.melt(id_vars="date", var_name="feature", value_name="value").dropna(subset=["value"])
        long.insert(0, "ticker", ticker)
        store.save_features(long)

        latest = f.dropna().tail(1)
        if latest.empty:
            excluded.append((ticker, "no fully-populated feature row (insufficient history)"))
            continue
        latest = latest.copy()
        latest.insert(0, "ticker", ticker)
        latest_rows.append(latest)

    ql_df = quality.to_log_frame(all_quality_results, run_date)
    store.save_quality_log(ql_df, run_date)

    print(f"\nQuality gate: {len(latest_rows)} passed, {len(excluded)} excluded")
    for t, reason in excluded[:10]:
        print(f"  excluded {t}: {reason}")
    if len(excluded) > 10:
        print(f"  ... and {len(excluded) - 10} more (see quality_log table)")

    if not latest_rows:
        print("Nothing to rank -- every ticker failed the quality gate.")
        store.close()
        return

    # -- Regime v2: needs the full cross-section, so it runs here, after
    #    ingestion, not before it like the old index-only v0.1 version.
    close_wide = pd.DataFrame(close_by_ticker).sort_index()
    returns_wide = close_wide.pct_change()
    regime_table = rg.build_regime_table(index_df, returns_wide, close_wide)
    regime_info = rg.latest_regime(regime_table)
    regime_label = regime_info["regime"]
    print(f"\nRegime: {regime_label}  |  HMM vol={regime_info['hmm_vol_state']} "
          f"(conf={regime_info['hmm_confidence']})  |  GMM vol={regime_info['gmm_vol_state']}  |  "
          f"ADX={regime_info['adx_14']}  |  avg pairwise corr={regime_info['avg_pairwise_corr']}  |  "
          f"breadth={regime_info['breadth_pct_above_ma20']}")

    latest_features = pd.concat(latest_rows, ignore_index=True)

    # Optional extra dimensions -- only present if run_market_intel.py has
    # been run. Missing entirely -> rank.py drops the weight and
    # renormalises. Present but sparse (most tickers have zero bulk deals
    # on any given day) -> those tickers get a neutral 0, not excluded.
    opt = store.latest_options_features()
    if not opt.empty:
        latest_features = latest_features.merge(opt[["ticker", "oi_score"]], on="ticker", how="left")
    flow = store.latest_institutional_flow()
    if not flow.empty:
        latest_features = latest_features.merge(flow[["ticker", "if_score"]], on="ticker", how="left")
        latest_features["if_score"] = latest_features["if_score"].fillna(0.0)

    ranked = rank.rank_universe(latest_features, uni, regime_label, run_date)

    # Persist the full ranked frame (base score + the raw weighted dimensions);
    # storage reindexes to its fixed schema, so a downstream reader gets the
    # dimension breakdown from the DB, not just the CSV. Regime diagnostics land
    # in their own one-row-per-run table for the same reason.
    store.save_rankings(ranked)
    store.save_regime(regime_info, run_date)

    out_path = config.OUTPUT_DIR / f"rankings_{run_date}.csv"
    ranked.to_csv(out_path, index=False)  # full frame, incl. raw feature inputs
    print(f"\nWrote {out_path} ({len(ranked)} ranked tickers)")

    print("\nTop 15:")
    print(ranked.head(15).to_string(index=False))

    store.close()
    return ranked


if __name__ == "__main__":
    main(demo="--demo" in sys.argv)
