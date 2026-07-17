"""
Loads the tradeable universe from config.UNIVERSE_CSV.

Tolerant of two schemas so you can point this at either the 50-stock
seed (ticker,name,sector) or the real F&O list (SYMBOL,COMPANY_NAME) --
or your own export from NSE/a screener -- without touching any other
module.
"""
import pandas as pd

import config


def load_universe() -> pd.DataFrame:
    """Returns a DataFrame with columns [ticker, name, sector]."""
    df = pd.read_csv(config.UNIVERSE_CSV)
    cols = {c.lower(): c for c in df.columns}

    if "symbol" in cols:
        out = pd.DataFrame({
            "ticker": df[cols["symbol"]].astype(str).str.strip(),
            "name": df[cols.get("company_name", cols["symbol"])].astype(str).str.strip(),
        })
    elif "ticker" in cols:
        out = pd.DataFrame({
            "ticker": df[cols["ticker"]].astype(str).str.strip(),
            "name": df[cols.get("name", cols["ticker"])].astype(str).str.strip(),
        })
    else:
        raise ValueError(
            f"{config.UNIVERSE_CSV} needs either a 'SYMBOL'/'COMPANY_NAME' "
            "or a 'ticker'/'name' column."
        )

    out["sector"] = df[cols["sector"]].astype(str).str.strip() if "sector" in cols else "Unclassified"
    out = out.drop_duplicates(subset="ticker").reset_index(drop=True)
    return out
