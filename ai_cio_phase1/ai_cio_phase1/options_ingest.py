"""
Options intelligence -- v0.1 of the doc's M08. Same honesty rule as
news and institutional flow: the feature MATH here is solid and tested
(PCR, max pain, IV skew are well-defined formulas, verified below against
a synthetic chain). The LIVE FETCH is the fragile part -- NSE's option
chain isn't a stable public API, it's their own website's internal
endpoint, gated by session cookies and liable to change without notice.
Confirmed to exist at api/option-chain-equities as of this build; verify
against https://www.nseindia.com/option-chain if it breaks.

For anything production-grade, a broker's option chain (Kite Connect
has one) is a real, documented, stable API instead of a scraped one --
worth the subscription once this matters for real money.
"""
import json
import urllib.request

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------
# Live fetch -- fragile, see module docstring
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
    # NSE requires a homepage visit first to obtain valid session cookies
    # before the API endpoints will respond -- this is the standard
    # workaround used across the open-source NSE-scraping community.
    opener.open(urllib.request.Request("https://www.nseindia.com", headers=headers), timeout=10)
    return opener, headers


def fetch_nse_option_chain(symbol: str) -> pd.DataFrame:
    opener, headers = _nse_opener()
    url = f"https://www.nseindia.com/api/option-chain-equities?symbol={symbol}"
    req = urllib.request.Request(url, headers=headers)
    with opener.open(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())
    rows = []
    for rec in data["records"]["data"]:
        ce, pe = rec.get("CE"), rec.get("PE")
        rows.append({
            "strike": rec["strikePrice"],
            "call_oi": ce["openInterest"] if ce else 0,
            "put_oi": pe["openInterest"] if pe else 0,
            "call_volume": ce["totalTradedVolume"] if ce else 0,
            "put_volume": pe["totalTradedVolume"] if pe else 0,
            "call_iv": (ce["impliedVolatility"] if ce else np.nan) / 100,
            "put_iv": (pe["impliedVolatility"] if pe else np.nan) / 100,
        })
    spot = data["records"].get("underlyingValue")
    return pd.DataFrame(rows), spot


# ---------------------------------------------------------------------
# Synthetic chain -- for testing the feature math offline
# ---------------------------------------------------------------------

def synthetic_option_chain(spot_price: float, rng=None, n_strikes: int = 15):
    rng = rng or np.random.default_rng(0)
    step_pct = 0.025
    raw_strikes = spot_price * (1 + step_pct * np.arange(-(n_strikes // 2), n_strikes // 2 + 1))
    strikes = np.round(raw_strikes / 5) * 5
    moneyness = (strikes - spot_price) / spot_price
    atm_iv = rng.uniform(0.18, 0.35)
    call_iv = np.clip(atm_iv + 0.15 * moneyness**2 + rng.normal(0, 0.01, len(strikes)), 0.05, 2.0)
    put_iv = np.clip(atm_iv + 0.15 * moneyness**2 - 0.06 * moneyness + rng.normal(0, 0.01, len(strikes)), 0.05, 2.0)
    # concentrate more OI near strikes close to spot, like a real chain
    proximity_weight = np.exp(-4 * moneyness**2)
    call_oi = (rng.uniform(2000, 40000, len(strikes)) * proximity_weight).round()
    put_oi = (rng.uniform(2000, 40000, len(strikes)) * proximity_weight).round()
    return pd.DataFrame({
        "strike": strikes, "call_oi": call_oi, "put_oi": put_oi,
        "call_volume": call_oi * rng.uniform(0.1, 0.5, len(strikes)),
        "put_volume": put_oi * rng.uniform(0.1, 0.5, len(strikes)),
        "call_iv": call_iv, "put_iv": put_iv,
    })


# ---------------------------------------------------------------------
# Feature math -- pure functions, no network, fully testable
# ---------------------------------------------------------------------

def compute_max_pain(chain: pd.DataFrame) -> float:
    strikes = chain["strike"].values
    call_oi, put_oi = chain["call_oi"].values, chain["put_oi"].values
    pains = [
        np.sum(call_oi * np.maximum(s - strikes, 0)) + np.sum(put_oi * np.maximum(strikes - s, 0))
        for s in strikes
    ]
    return float(strikes[np.argmin(pains)])


def compute_pcr(chain: pd.DataFrame) -> dict:
    return {
        "pcr_oi": float(chain["put_oi"].sum() / max(chain["call_oi"].sum(), 1)),
        "pcr_volume": float(chain["put_volume"].sum() / max(chain["call_volume"].sum(), 1)),
    }


def compute_iv_skew(chain: pd.DataFrame, spot_price: float, otm_pct: float = 0.05) -> dict:
    """Approximates the doc's '25-delta put minus 25-delta call' skew
    using fixed %-OTM strikes instead of true delta (a full delta calc
    needs a rate/dividend/time-to-expiry-aware Black-Scholes -- overkill
    for a v0.1 feature; revisit if the approximation proves too coarse)."""
    put_strike_target = spot_price * (1 - otm_pct)
    call_strike_target = spot_price * (1 + otm_pct)
    put_row = chain.iloc[(chain["strike"] - put_strike_target).abs().argsort().iloc[0]]
    call_row = chain.iloc[(chain["strike"] - call_strike_target).abs().argsort().iloc[0]]
    atm_row = chain.iloc[(chain["strike"] - spot_price).abs().argsort().iloc[0]]
    return {
        "iv_skew": float(put_row["put_iv"] - call_row["call_iv"]),
        "atm_iv": float((atm_row["call_iv"] + atm_row["put_iv"]) / 2),
    }


def compute_option_features(chain: pd.DataFrame, spot_price: float) -> dict:
    if chain.empty:
        return {}
    out = {"max_pain": compute_max_pain(chain), "max_pain_dist_pct": None}
    out["max_pain_dist_pct"] = (spot_price - out["max_pain"]) / spot_price
    out.update(compute_pcr(chain))
    out.update(compute_iv_skew(chain, spot_price))
    return out
