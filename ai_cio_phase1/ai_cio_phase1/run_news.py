"""
Run the news module standalone.

    python run_news.py                              # synthetic demo, fully offline, safe default
    python run_news.py --source google --limit 10    # real Google News RSS, first 10 tickers only
    python run_news.py --source finnhub --api-key XXX --limit 10

--limit matters for the real sources: don't point 176 sequential requests
at an unofficial endpoint (google) or an unverified symbol mapping
(finnhub) on your first run. Prove it on 10, then widen it.
"""
import argparse
import pandas as pd

import config
import universe as uv
import storage
import news_ingest as ni


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="synthetic", choices=["synthetic", "google", "finnhub"])
    parser.add_argument("--api-key", default=None, help="required for --source finnhub")
    parser.add_argument("--max-per-ticker", type=int, default=5)
    parser.add_argument("--sleep", type=float, default=None, help="seconds between tickers")
    parser.add_argument("--limit", type=int, default=None, help="only process the first N tickers")
    args = parser.parse_args()

    uni = uv.load_universe()
    if args.limit:
        uni = uni.head(args.limit)

    if args.source == "synthetic":
        fetch_fn, default_sleep = ni.fetch_synthetic_news, 0.0
    elif args.source == "google":
        fetch_fn, default_sleep = ni.fetch_google_news_rss, 1.0
    else:
        if not args.api_key:
            raise SystemExit("--api-key is required for --source finnhub (get a free one at finnhub.io)")
        fetch_fn = lambda t, c, n: ni.fetch_finnhub_news(t, c, n, api_key=args.api_key)
        default_sleep = 0.3

    sleep_s = args.sleep if args.sleep is not None else default_sleep
    print(f"Fetching news for {len(uni)} tickers via '{args.source}' (sleep={sleep_s}s/ticker) ...")
    news_df = ni.fetch_news_for_universe(uni, fetch_fn, max_per_ticker=args.max_per_ticker, sleep_s=sleep_s)

    store = storage.Store()
    store.save_news(news_df)
    store.close()

    n_total = len(news_df)
    n_dupe = int(news_df["is_duplicate"].sum()) if "is_duplicate" in news_df else 0
    n_err = int((news_df["fetch_error"] != "").sum()) if "fetch_error" in news_df else 0
    print(f"\n{n_total} rows fetched | {n_dupe} flagged duplicate | {n_err} fetch errors")
    if "sentiment_label" in news_df and n_total:
        print(news_df["sentiment_label"].value_counts().to_string())

    out_path = config.OUTPUT_DIR / f"news_{args.source}_{pd.Timestamp.today().date()}.csv"
    news_df.to_csv(out_path, index=False)
    print(f"Wrote {out_path}")
    return news_df


if __name__ == "__main__":
    main()
