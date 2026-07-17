"""
Data quality gate, in the spirit of the doc's Part 19 self-critique on
data quality risk: never let one bad-data ticker quietly corrupt a
ranking. Hard checks exclude a ticker from today's ranking; soft checks
are logged but don't block.
"""
import pandas as pd

import config


def run_quality_checks(df: pd.DataFrame, ticker: str, lookback: int = 60) -> list[dict]:
    """Returns a list of check result dicts. Each has:
    check_name, passed (bool), severity ('hard' | 'soft'), detail (str)
    """
    results = []
    if df.empty:
        return [{"check_name": "has_data", "passed": False, "severity": "hard",
                  "detail": "no rows returned"}]

    window_start = df["date"].max() - pd.Timedelta(days=int(lookback * 1.6))
    recent = df[df["date"] >= window_start]

    # 1. Missing days vs expected trading calendar (same window on both sides)
    expected = pd.bdate_range(start=window_start, end=df["date"].max())
    missing_frac = 1 - (recent["date"].isin(expected).sum() / max(len(expected), 1))
    results.append({
        "check_name": "missing_days", "severity": "hard",
        "passed": missing_frac <= 0.03,
        "detail": f"{missing_frac:.1%} of expected trading days missing in last {lookback}d",
    })

    # 2. Staleness -- is the last bar recent?
    gap_days = (pd.Timestamp.today().normalize() - df["date"].max()).days
    results.append({
        "check_name": "staleness", "severity": "hard",
        "passed": gap_days <= 5,
        "detail": f"last bar is {gap_days}d old",
    })

    # 3. Price sanity
    bad_price = (df["close"] <= 0).any() or (df["high"] < df["low"]).any()
    results.append({
        "check_name": "price_sanity", "severity": "hard",
        "passed": not bad_price,
        "detail": "non-positive close or high<low found" if bad_price else "ok",
    })

    # 4. Volume sanity (soft -- illiquid small-caps can legitimately have thin days)
    zero_vol_frac = (recent["volume"] == 0).mean() if len(recent) else 1.0
    results.append({
        "check_name": "volume_sanity", "severity": "soft",
        "passed": zero_vol_frac <= 0.10,
        "detail": f"{zero_vol_frac:.1%} zero-volume days in last {lookback}d",
    })

    # 5. Extreme single-day moves (soft -- flag for review, don't exclude;
    #    could be a real gap or an un-adjusted corporate action)
    ret = df["close"].pct_change().abs()
    extreme = ret.max() if len(ret) else 0
    results.append({
        "check_name": "extreme_move", "severity": "soft",
        "passed": extreme <= 0.40,
        "detail": f"largest single-day move: {extreme:.1%}",
    })

    for r in results:
        r["ticker"] = ticker
    return results


def passes_hard_gate(check_results: list[dict]) -> bool:
    return all(r["passed"] for r in check_results if r["severity"] == "hard")


def to_log_frame(all_results: dict[str, list[dict]], run_date) -> pd.DataFrame:
    rows = []
    for ticker, checks in all_results.items():
        for c in checks:
            rows.append({
                "ticker": ticker, "run_date": run_date, "check_name": c["check_name"],
                "passed": c["passed"], "severity": c["severity"], "detail": c["detail"],
            })
    return pd.DataFrame(rows)
