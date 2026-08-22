"""
Zerodha Kite Connect adapter -- the standard path once yfinance's free
daily bars aren't enough (intraday data, real order-book depth, or just
a more reliable/licensed feed). Chosen over Upstox/Dhan/Fyers only
because it's the one the original doc's own data-source table (Part 3.1)
and most retail-quant tooling treats as the reference implementation --
the other three follow a similar shape if you'd rather use one of them.

This needs the `kiteconnect` package (`pip install kiteconnect`) and a
paid API subscription from developers.kite.trade (~Rs 2000/month, per
the doc's own numbers). The login flow below is INTERACTIVE by design --
Kite's OAuth-style flow requires a browser redirect and cannot be
automated headlessly, and reimplementing it as a scripted bypass would
violate Kite's terms. Run login_flow_instructions() once per day (access
tokens expire daily), then reuse the resulting access_token for the rest
of that session.
"""
import pandas as pd

import config


def login_flow_instructions(api_key: str) -> str:
    """Returns what to print/show the user -- the actual login happens
    in their browser, not in this process."""
    return (
        "1. pip install kiteconnect\n"
        "2. from kiteconnect import KiteConnect; kite = KiteConnect(api_key='...')\n"
        f"3. Open kite.login_url() in a browser and log in: this redirects to your\n"
        "   registered redirect URL with a `request_token` in the query string.\n"
        "4. data = kite.generate_session(request_token, api_secret='...')\n"
        "   kite.set_access_token(data['access_token'])\n"
        "5. Pass this authenticated `kite` object into the functions below.\n"
        "   The access_token is valid until ~6am IST the next day -- re-run this\n"
        "   once per trading day, it's not a one-time setup."
    )


_instrument_cache = None


def _instrument_token(kite_client, ticker: str) -> int:
    """Kite's historical_data() needs a numeric instrument_token, not a
    ticker symbol -- this looks it up from the NSE instrument master
    (cached in-process since it's ~2MB and doesn't change intraday)."""
    global _instrument_cache
    if _instrument_cache is None:
        instruments = kite_client.instruments("NSE")
        _instrument_cache = {i["tradingsymbol"]: i["instrument_token"] for i in instruments}
    if ticker not in _instrument_cache:
        raise KeyError(f"{ticker} not found in NSE instrument master -- check the symbol")
    return _instrument_cache[ticker]


def get_ohlcv_kite(kite_client, ticker: str, n_days: int = None, interval: str = "day") -> pd.DataFrame:
    n_days = n_days or config.HISTORY_TRADING_DAYS
    token = _instrument_token(kite_client, ticker)
    to_date = pd.Timestamp.today().normalize()
    from_date = to_date - pd.Timedelta(days=int(n_days * 1.6) + 10)
    records = kite_client.historical_data(token, from_date, to_date, interval)
    if not records:
        raise RuntimeError(f"Kite returned no historical data for {ticker} (token {token})")
    df = pd.DataFrame(records).rename(columns={"date": "date"})
    df["date"] = pd.to_datetime(df["date"]).dt.tz_localize(None)
    return df[["date", "open", "high", "low", "close", "volume"]].tail(n_days).reset_index(drop=True)
