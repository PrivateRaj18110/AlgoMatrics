"""
AI-CIO Phase 1 -- configuration.

Everything that changes between "demo on my laptop" and "real run against
NSE" lives here. The rest of the codebase just reads these values -- it
does not know or care whether the data behind it is synthetic or real.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
# Defaults to a file next to the code for a laptop run. Set AICIO_DB_PATH to
# point the pipeline at a shared location (e.g. a mounted volume) that a
# separate reader process consumes -- no code change needed.
DB_PATH = Path(os.environ.get("AICIO_DB_PATH", str(ROOT / "aicio.duckdb")))

# Source of truth for the tradeable universe. Treat this as versioned
# config data, not something to scrape live on every run -- NSE's F&O
# eligibility list is reviewed quarterly and their website blocks naive
# scripted requests without a proper session. Update this file by hand
# (or via nsepython / jugaad-data) every quarter, not at runtime.
#
# universe_fo.csv  -- the real ~176-stock NSE F&O list (columns: SYMBOL,
#                      COMPANY_NAME). This is the primary universe.
# universe_seed.csv -- older 50-stock starter with a sector column, kept
#                      only as a smaller fallback for quick smoke tests.
UNIVERSE_CSV = DATA_DIR / "universe_fo.csv"

# Benchmark used for beta / relative-strength calculations.
INDEX_TICKER = "^NSEI"        # Nifty 50, yfinance symbol
INDEX_NAME = "NIFTY50"

# How much history to pull / simulate.
HISTORY_TRADING_DAYS = 750    # ~3 years, enough for the 252d window features

# Rolling windows shared across the feature and regime modules (trading days).
WINDOW_SHORT = 5
WINDOW_MED = 20
WINDOW_LONG = 60
WINDOW_VLONG = 252

# "synthetic"  -> generates realistic fake OHLCV locally, no network needed.
#                 This is what runs in this sandbox and is a fine way to
#                 sanity-check the pipeline before you have real data.
# "yfinance"   -> pulls real daily OHLCV via Yahoo Finance (.NS suffix).
#                 Needs outbound internet access to Yahoo's endpoints,
#                 which this sandbox does not have.
DATA_SOURCE = os.environ.get("AICIO_DATA_SOURCE", "synthetic")

# Regime-adjusted ranking weights (Part 8.2 of the doc). Keys match the
# labels regime.py produces. This is the piece that makes a regime
# engine worth having -- a regime label nothing downstream reacts to is
# just a string. Falls back to DEFAULT_WEIGHTS for any label not listed
# (keeps this from breaking if regime.py's label set changes upstream).
DEFAULT_WEIGHTS = {
    "rs_60d": 0.28, "mom_20d": 0.16, "turnover_20d_avg": 0.16,
    "atr_pct": 0.12, "hv_ratio_10_60": 0.08, "oi_score": 0.10, "if_score": 0.10,
}

REGIME_WEIGHTS = {
    # Trending regimes: momentum/RS carries more weight, more so as vol
    # rises; institutional flow (if_score) matters more in a clear trend
    # than in chop, per the doc's own framing of IF as directional
    # conviction evidence.
    "trending_low":    {"rs_60d": 0.32, "mom_20d": 0.20, "turnover_20d_avg": 0.12, "atr_pct": 0.08, "hv_ratio_10_60": 0.08, "oi_score": 0.05, "if_score": 0.15},
    "trending_normal": {"rs_60d": 0.28, "mom_20d": 0.16, "turnover_20d_avg": 0.12, "atr_pct": 0.16, "hv_ratio_10_60": 0.08, "oi_score": 0.05, "if_score": 0.15},
    "trending_high":   {"rs_60d": 0.20, "mom_20d": 0.12, "turnover_20d_avg": 0.16, "atr_pct": 0.24, "hv_ratio_10_60": 0.08, "oi_score": 0.05, "if_score": 0.15},
    # Ranging regimes: momentum is weaker (doc favours mean-reversion
    # instead), so RS/momentum gets down-weighted. OI dominates in
    # ranging low-vol specifically, matching the doc's own R3 row (40%
    # options weight) -- that's when premium-selling/options strategies
    # are what's actually working, so options positioning is the signal.
    "ranging_low":     {"rs_60d": 0.10, "mom_20d": 0.06, "turnover_20d_avg": 0.10, "atr_pct": 0.06, "hv_ratio_10_60": 0.28, "oi_score": 0.35, "if_score": 0.05},
    "ranging_normal":  {"rs_60d": 0.14, "mom_20d": 0.08, "turnover_20d_avg": 0.14, "atr_pct": 0.14, "hv_ratio_10_60": 0.20, "oi_score": 0.20, "if_score": 0.10},
    "ranging_high":    {"rs_60d": 0.06, "mom_20d": 0.04, "turnover_20d_avg": 0.22, "atr_pct": 0.26, "hv_ratio_10_60": 0.14, "oi_score": 0.08, "if_score": 0.20},  # doc: "no clear edge -- reduce sizes"
    # Correlation-driven regimes override trend/vol per the doc's design
    "risk_on":            {"rs_60d": 0.35, "mom_20d": 0.20, "turnover_20d_avg": 0.10, "atr_pct": 0.03, "hv_ratio_10_60": 0.07, "oi_score": 0.05, "if_score": 0.20},
    "risk_off":           {"rs_60d": 0.03, "mom_20d": 0.03, "turnover_20d_avg": 0.28, "atr_pct": 0.28, "hv_ratio_10_60": 0.08, "oi_score": 0.05, "if_score": 0.25},  # doc: R6 -- smart-money direction matters most in stress
    "recovery_transition": {"rs_60d": 0.10, "mom_20d": 0.08, "turnover_20d_avg": 0.22, "atr_pct": 0.12, "hv_ratio_10_60": 0.20, "oi_score": 0.10, "if_score": 0.18},  # doc: small sizes, cautious
}

DATE_FMT = "%Y-%m-%d"
