"""NSE index constituent groups, for filtering AI-CIO rankings to an index.

Reference data (framework-free). These are **snapshots** — NSE reviews index
membership periodically, so update them (and the AI-CIO universe) each quarter.
A symbol that is not in the AI-CIO universe is simply never matched, so a stale
entry is harmless; a missing one just won't appear under that index.
"""

from __future__ import annotations

NIFTY_50: frozenset[str] = frozenset(
    {
        "RELIANCE",
        "HDFCBANK",
        "ICICIBANK",
        "INFY",
        "TCS",
        "ITC",
        "LT",
        "BHARTIARTL",
        "SBIN",
        "AXISBANK",
        "KOTAKBANK",
        "HINDUNILVR",
        "BAJFINANCE",
        "ASIANPAINT",
        "MARUTI",
        "SUNPHARMA",
        "TITAN",
        "ULTRACEMCO",
        "NESTLEIND",
        "WIPRO",
        "ONGC",
        "NTPC",
        "POWERGRID",
        "M&M",
        "TATAMOTORS",
        "TATASTEEL",
        "JSWSTEEL",
        "ADANIENT",
        "ADANIPORTS",
        "COALINDIA",
        "HCLTECH",
        "TECHM",
        "GRASIM",
        "HINDALCO",
        "DRREDDY",
        "CIPLA",
        "BAJAJFINSV",
        "BAJAJ-AUTO",
        "EICHERMOT",
        "HEROMOTOCO",
        "BPCL",
        "BRITANNIA",
        "APOLLOHOSP",
        "INDUSINDBK",
        "SBILIFE",
        "HDFCLIFE",
        "TATACONSUM",
        "LTIM",
        "SHRIRAMFIN",
        "TRENT",
    }
)

NIFTY_NEXT_50: frozenset[str] = frozenset(
    {
        "ADANIGREEN",
        "ADANIPOWER",
        "ADANIENSOL",
        "AMBUJACEM",
        "DMART",
        "BAJAJHLDNG",
        "BANKBARODA",
        "BEL",
        "BOSCHLTD",
        "CANBK",
        "CGPOWER",
        "CHOLAFIN",
        "COLPAL",
        "DABUR",
        "DIVISLAB",
        "DLF",
        "GAIL",
        "GODREJCP",
        "HAVELLS",
        "HAL",
        "ICICIGI",
        "ICICIPRULI",
        "IOC",
        "INDIGO",
        "NAUKRI",
        "JINDALSTEL",
        "JIOFIN",
        "JSWENERGY",
        "LICI",
        "MARICO",
        "MOTHERSON",
        "MUTHOOTFIN",
        "PIDILITIND",
        "PFC",
        "PNB",
        "RECLTD",
        "SIEMENS",
        "SHREECEM",
        "SRF",
        "TATAPOWER",
        "TORNTPHARM",
        "TVSMOTOR",
        "UNITDSPR",
        "VBL",
        "VEDL",
        "ZOMATO",
        "ZYDUSLIFE",
        "IRFC",
        "INDUSTOWER",
        "LODHA",
    }
)

BANK_NIFTY: frozenset[str] = frozenset(
    {
        "HDFCBANK",
        "ICICIBANK",
        "SBIN",
        "KOTAKBANK",
        "AXISBANK",
        "INDUSINDBK",
        "BANKBARODA",
        "PNB",
        "AUBANK",
        "FEDERALBNK",
        "IDFCFIRSTB",
        "CANBK",
    }
)

FIN_NIFTY: frozenset[str] = frozenset(
    {
        "HDFCBANK",
        "ICICIBANK",
        "AXISBANK",
        "KOTAKBANK",
        "SBIN",
        "BAJFINANCE",
        "BAJAJFINSV",
        "SHRIRAMFIN",
        "PFC",
        "HDFCLIFE",
        "RECLTD",
        "SBILIFE",
        "HDFCAMC",
        "CHOLAFIN",
        "ICICIGI",
        "ICICIPRULI",
        "MUTHOOTFIN",
        "SBICARD",
        "LICHSGFIN",
        "JIOFIN",
    }
)

# (value, label) in display order; the console prepends an "All" option itself.
INDEX_GROUPS: tuple[tuple[str, str], ...] = (
    ("nifty50", "Nifty 50"),
    ("niftynext50", "Nifty Next 50"),
    ("banknifty", "Bank Nifty"),
    ("finnifty", "Fin Nifty"),
)

_BY_VALUE: dict[str, frozenset[str]] = {
    "nifty50": NIFTY_50,
    "niftynext50": NIFTY_NEXT_50,
    "banknifty": BANK_NIFTY,
    "finnifty": FIN_NIFTY,
}


def symbols_for_index(value: str) -> frozenset[str] | None:
    """Constituent symbols for an index group value, or ``None`` if unknown."""
    return _BY_VALUE.get(value.strip().lower())
