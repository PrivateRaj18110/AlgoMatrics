"""
Institutional flow -- v0.1 of the doc's M22 (institutional flow) / M23
(dark pool -- skipped entirely: that's FINRA/US market structure, no
real NSE equivalent exists, so there's nothing honest to build there for
this universe). Bulk and block deals ARE genuinely public: SEBI mandates
same-day disclosure, and NSE's large-deal endpoint is confirmed to exist
at api/snapshot-capital-market-largedeal. Same session-cookie fragility
as the options module -- this is NSE's own site, not a stable contract.

FII/DII aggregate flow (also in the doc's M22 input list) is a market-
wide number, not per-stock, and would need a different source (SEBI's
own FPI statistics) -- not built here since bulk/block deals already
cover the per-stock institutional-activity signal this phase needs.
"""
import json
import urllib.request

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------
# Live fetch -- fragile, see module docstring. Reuses the same
# session-cookie pattern as options_ingest.py (same site, same gate).
# ---------------------------------------------------------------------

def _nse_opener():
    import http.cookiejar
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "application/json",
    }
    opener.open(urllib.request.Request("https://www.nseindia.com", headers=headers), timeout=10)
    return opener, headers


def fetch_nse_bulk_deals(band_type: str = "bulk_deals") -> pd.DataFrame:
    """band_type: 'bulk_deals', 'block_deals', or 'short_selling'."""
    opener, headers = _nse_opener()
    url = f"https://www.nseindia.com/api/snapshot-capital-market-largedeal?index={band_type}"
    req = urllib.request.Request(url, headers=headers)
    with opener.open(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
    rows = data.get(band_type, data) if isinstance(data, dict) else data
    df = pd.DataFrame(rows)
    rename = {"symbol": "ticker", "clientName": "client_name", "buySell": "buy_sell",
              "quantityTraded": "quantity", "tradePrice": "price", "date": "date"}
    return df.rename(columns={k: v for k, v in rename.items() if k in df.columns})


# ---------------------------------------------------------------------
# Synthetic deals -- for testing the aggregation logic offline. Client
# names are deliberately fake, same reasoning as the news module: never
# fabricate anything that could be mistaken for a real institution.
# ---------------------------------------------------------------------

_DEMO_CLIENTS = ["DEMO-FUND-A", "DEMO-FUND-B", "DEMO-FII-1", "DEMO-DII-1"]


def synthetic_bulk_deals(universe_df: pd.DataFrame, rng=None, n_deals: int = 300) -> pd.DataFrame:
    rng = rng or np.random.default_rng(3)
    tickers = rng.choice(universe_df["ticker"].values, size=n_deals)
    rows = []
    for t in tickers:
        rows.append({
            "date": pd.Timestamp.today().normalize(),
            "ticker": t,
            "client_name": rng.choice(_DEMO_CLIENTS),
            "buy_sell": rng.choice(["BUY", "SELL"]),
            "quantity": int(rng.integers(10_000, 500_000)),
            "price": float(rng.uniform(50, 4000)),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------
# Aggregation -- pure function, no network, fully testable
# ---------------------------------------------------------------------

def aggregate_institutional_bias(deals: pd.DataFrame) -> pd.DataFrame:
    """One row per ticker: net signed value, deal count, and a
    normalised bias score in [-1, 1] (net signed value / gross value) --
    the M22 output ('institutional bias per instrument')."""
    if deals.empty:
        return pd.DataFrame(columns=["ticker", "net_value", "gross_value", "n_deals", "bias_score"])
    d = deals.copy()
    d["signed_value"] = np.where(d["buy_sell"].str.upper() == "BUY", 1, -1) * d["quantity"] * d["price"]
    d["abs_value"] = d["quantity"] * d["price"]
    agg = d.groupby("ticker").agg(
        net_value=("signed_value", "sum"),
        gross_value=("abs_value", "sum"),
        n_deals=("signed_value", "count"),
    ).reset_index()
    agg["bias_score"] = agg["net_value"] / agg["gross_value"].replace(0, np.nan)
    return agg
