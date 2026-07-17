"""
Run options intelligence + institutional flow for the universe.
Needs run_pipeline.py to have run at least once already (uses the
latest stored close price per ticker as the options chain's spot price).

    python run_market_intel.py                 # synthetic, offline, safe default
    python run_market_intel.py --source real --limit 10   # real NSE fetch, first 10 tickers

--limit matters a lot more here than for news: NSE's option-chain and
large-deal endpoints are the most fragile, most bot-hostile of every
source in this project. Prove --source real works on 10 names before
even considering pointing it at the full universe.
"""
import argparse
import numpy as np
import pandas as pd

import config
import universe as uv
import storage
import options_ingest as oi
import institutional_flow as ifl


def run_synthetic(uni: pd.DataFrame, spot_by_ticker: dict, rng: np.random.Generator):
    opt_rows = []
    for _, row in uni.iterrows():
        ticker = row["ticker"]
        spot = spot_by_ticker.get(ticker)
        if spot is None or spot <= 0:
            continue
        chain = oi.synthetic_option_chain(spot, rng=rng)
        feats = oi.compute_option_features(chain, spot)
        feats["ticker"] = ticker
        feats["oi_score"] = -feats["pcr_oi"]  # inverted PCR: fewer puts relative to calls = more bullish
        opt_rows.append(feats)
    opt_df = pd.DataFrame(opt_rows)

    deals = ifl.synthetic_bulk_deals(uni, rng=rng, n_deals=300)
    if_df = ifl.aggregate_institutional_bias(deals)
    if_df["if_score"] = if_df["bias_score"]
    return opt_df, if_df


def run_real(uni: pd.DataFrame, limit: int = None):
    if limit:
        uni = uni.head(limit)
    opt_rows = []
    for _, row in uni.iterrows():
        try:
            chain, spot = oi.fetch_nse_option_chain(row["ticker"])
            feats = oi.compute_option_features(chain, spot)
            feats["ticker"] = row["ticker"]
            feats["oi_score"] = -feats["pcr_oi"]
            opt_rows.append(feats)
        except Exception as e:
            print(f"  {row['ticker']}: options fetch failed ({e})")
    opt_df = pd.DataFrame(opt_rows)

    try:
        deals = ifl.fetch_nse_bulk_deals("bulk_deals")
        if_df = ifl.aggregate_institutional_bias(deals)
        if_df["if_score"] = if_df["bias_score"]
    except Exception as e:
        print(f"  bulk deals fetch failed ({e})")
        if_df = pd.DataFrame(columns=["ticker", "net_value", "gross_value", "n_deals", "if_score"])
    return opt_df, if_df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="synthetic", choices=["synthetic", "real"])
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    run_date = pd.Timestamp.today().normalize().date()
    uni = uv.load_universe()
    store = storage.Store()

    if args.source == "synthetic":
        latest_close = store.con.execute(
            "SELECT ticker, close FROM ohlcv WHERE (ticker, date) IN "
            "(SELECT ticker, max(date) FROM ohlcv GROUP BY ticker)"
        ).df()
        spot_by_ticker = dict(zip(latest_close["ticker"], latest_close["close"]))
        rng = np.random.default_rng(11)
        print(f"Generating synthetic options + institutional flow for {len(uni)} tickers ...")
        opt_df, if_df = run_synthetic(uni, spot_by_ticker, rng)
    else:
        print(f"Fetching REAL options + institutional flow (limit={args.limit}) ...")
        opt_df, if_df = run_real(uni, args.limit)

    store.save_options_features(opt_df, run_date)
    store.save_institutional_flow(if_df, run_date)
    store.close()

    print(f"\nOptions features: {len(opt_df)} tickers")
    if len(opt_df):
        print(opt_df[["ticker", "pcr_oi", "iv_skew", "max_pain_dist_pct", "oi_score"]]
              .sort_values("oi_score", ascending=False).head(5).to_string(index=False))
    print(f"\nInstitutional flow: {len(if_df)} tickers with at least one bulk/block deal today")
    if len(if_df):
        print(if_df[["ticker", "n_deals", "net_value", "if_score"]]
              .sort_values("if_score", ascending=False).head(5).to_string(index=False))

    opt_df.to_csv(config.OUTPUT_DIR / f"options_{args.source}_{run_date}.csv", index=False)
    if_df.to_csv(config.OUTPUT_DIR / f"institutional_flow_{args.source}_{run_date}.csv", index=False)
    return opt_df, if_df


if __name__ == "__main__":
    main()
