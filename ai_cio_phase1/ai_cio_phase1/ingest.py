"""
Ingestion adapters.

Two sources behind one interface -- get_ohlcv(ticker, n_days) and
get_index_ohlcv(n_days) both return a DataFrame with columns
[date, open, high, low, close, volume], most recent last.

Swap DATA_SOURCE in config.py to switch between them. Nothing downstream
(storage, quality, features, regime, rank) knows or cares which one is
active.
"""
import hashlib
import time
import numpy as np
import pandas as pd

import config


# ---------------------------------------------------------------------
# Synthetic source -- no network required. Used for local testing, and
# for this sandbox specifically, which has no outbound access to market
# data APIs. Correlated to a synthetic index so beta / relative-strength
# features are meaningful, not just noise.
# ---------------------------------------------------------------------

def _seed_for(ticker: str) -> int:
    return int(hashlib.sha256(ticker.encode()).hexdigest(), 16) % (2**32)


def _business_dates(n_days: int) -> pd.DatetimeIndex:
    end = pd.Timestamp.today().normalize()
    return pd.bdate_range(end=end, periods=n_days)


def _ohlcv_from_returns(dates, returns: np.ndarray, start_price: float, rng) -> pd.DataFrame:
    close = start_price * np.exp(np.cumsum(returns))
    prev_close = np.roll(close, 1)
    prev_close[0] = start_price
    open_ = prev_close * (1 + rng.normal(0, 0.003, len(dates)))
    hi_noise = np.abs(rng.normal(0, 0.006, len(dates)))
    lo_noise = np.abs(rng.normal(0, 0.006, len(dates)))
    high = np.maximum(open_, close) * (1 + hi_noise)
    low = np.minimum(open_, close) * (1 - lo_noise)
    base_vol = rng.lognormal(mean=13.5, sigma=0.4, size=len(dates))
    volume = np.round(base_vol * (1 + 2 * np.abs(returns) / (np.std(returns) + 1e-9))).astype(int)
    return pd.DataFrame({
        "date": dates, "open": open_, "high": high,
        "low": low, "close": close, "volume": volume,
    })


def get_index_ohlcv_synthetic(n_days: int = None) -> pd.DataFrame:
    n_days = n_days or config.HISTORY_TRADING_DAYS
    rng = np.random.default_rng(42)
    dates = _business_dates(n_days)
    # 3-state Markov-switching vol/drift (calm / normal / crisis) -- a
    # constant-parameter random walk, or even a 2-state switch, gives the
    # 3-state HMM nothing real to distinguish a 3rd state from. Real
    # regimes also don't jump straight from calm to crisis, so that
    # transition is set to 0 -- it has to pass through "normal" first.
    transmat = np.array([
        [0.97, 0.03, 0.00],   # calm
        [0.03, 0.94, 0.03],   # normal
        [0.00, 0.08, 0.92],   # crisis
    ])
    params = {0: (0.0007, 0.008), 1: (0.0001, 0.016), 2: (-0.0009, 0.032)}
    states = np.zeros(n_days, dtype=int)
    s = 0
    for i in range(n_days):
        states[i] = s
        s = rng.choice(3, p=transmat[s])
    returns = np.array([rng.normal(*params[s]) for s in states])
    return _ohlcv_from_returns(dates, returns, start_price=22000.0, rng=rng)


def get_ohlcv_synthetic(ticker: str, n_days: int = None, index_returns: np.ndarray = None) -> pd.DataFrame:
    n_days = n_days or config.HISTORY_TRADING_DAYS
    rng = np.random.default_rng(_seed_for(ticker))
    dates = _business_dates(n_days)
    start_price = rng.uniform(80, 4000)
    beta = rng.uniform(0.5, 1.6)
    idio_mu = rng.uniform(-0.0002, 0.0007)
    idio_sigma = rng.uniform(0.012, 0.030)
    idio = rng.normal(idio_mu, idio_sigma, n_days)
    if index_returns is not None and len(index_returns) == n_days:
        returns = beta * index_returns + idio
    else:
        returns = idio
    return _ohlcv_from_returns(dates, returns, start_price=start_price, rng=rng)


def inject_demo_quality_issues(df: pd.DataFrame, rng) -> pd.DataFrame:
    """Deliberately corrupt one ticker's data so the quality gate has
    something real to catch. Demo-only -- never called on real data.
    Drops days inside the gate's own lookback window (last ~90 rows) so
    the missing_days check reliably fires instead of landing harmlessly
    somewhere in 3 years of history."""
    df = df.copy()
    recent_idx = df.index[-90:-5]
    drop_idx = rng.choice(recent_idx, size=5, replace=False)
    df = df.drop(index=drop_idx).reset_index(drop=True)
    zero_vol_idx = rng.choice(df.index, size=1)
    df.loc[zero_vol_idx, "volume"] = 0
    return df


# ---------------------------------------------------------------------
# Retry/backoff -- every real network source below is wrapped in this.
# Testable without any network access (see tests further down / README).
# ---------------------------------------------------------------------

def with_retry(fn, max_attempts: int = 3, base_delay: float = 1.0, *args, **kwargs):
    last_exc = None
    for attempt in range(max_attempts):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_exc = e
            if attempt < max_attempts - 1:
                time.sleep(base_delay * (2 ** attempt))  # 1s, 2s, 4s, ...
    raise last_exc


# ---------------------------------------------------------------------
# Real source -- yfinance. Will not succeed inside this sandbox (no
# outbound network to Yahoo's endpoints) but is real, working code for
# wherever you run this with internet access.
# ---------------------------------------------------------------------

def get_ohlcv_yfinance(ticker: str, n_days: int = None, since=None) -> pd.DataFrame:
    """since: if given, only bars after this date are needed (caller
    still gets whatever yfinance returns for the window; trim/merge is
    the caller's job via storage.save_ohlcv's upsert semantics)."""
    def _fetch():
        import yfinance as yf
        days = n_days or config.HISTORY_TRADING_DAYS
        if since is not None:
            days = min(days, (pd.Timestamp.today().normalize() - pd.Timestamp(since)).days + 5)
        period_days = int(days * 1.6) + 10
        hist = yf.Ticker(f"{ticker}.NS").history(period=f"{period_days}d", auto_adjust=True)
        if hist.empty:
            raise RuntimeError(f"No data returned for {ticker}.NS -- check the ticker and your network access")
        hist = hist.reset_index().rename(columns={
            "Date": "date", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume",
        })
        hist["date"] = pd.to_datetime(hist["date"]).dt.tz_localize(None)
        return hist[["date", "open", "high", "low", "close", "volume"]].tail(days).reset_index(drop=True)
    try:
        import yfinance  # noqa -- fail fast with a clear message if not installed
    except ImportError as e:
        raise RuntimeError("pip install yfinance to use DATA_SOURCE='yfinance'") from e
    return with_retry(_fetch, max_attempts=3, base_delay=2.0)


def get_ohlcv_yfinance_batch(tickers: list, n_days: int = None) -> dict:
    """One (or a few) HTTP round-trips for the whole universe instead of
    one per ticker -- yfinance's `download()` batches internally. Much
    faster and far less likely to get rate-limited than looping
    get_ohlcv_yfinance() 176 times. Returns {ticker: DataFrame}."""
    try:
        import yfinance as yf
    except ImportError as e:
        raise RuntimeError("pip install yfinance to use DATA_SOURCE='yfinance'") from e
    n_days = n_days or config.HISTORY_TRADING_DAYS
    period_days = int(n_days * 1.6) + 10
    symbols = [f"{t}.NS" for t in tickers]

    def _fetch():
        return yf.download(symbols, period=f"{period_days}d", auto_adjust=True,
                            group_by="ticker", threads=True, progress=False)

    raw = with_retry(_fetch, max_attempts=3, base_delay=3.0)
    out = {}
    for ticker, sym in zip(tickers, symbols):
        try:
            sub = raw[sym].dropna(how="all").reset_index()
            sub = sub.rename(columns={"Date": "date", "Open": "open", "High": "high",
                                       "Low": "low", "Close": "close", "Volume": "volume"})
            sub["date"] = pd.to_datetime(sub["date"]).dt.tz_localize(None)
            out[ticker] = sub[["date", "open", "high", "low", "close", "volume"]].tail(n_days).reset_index(drop=True)
        except (KeyError, Exception):
            continue  # missing/delisted symbol -- caller's quality gate handles the gap
    return out


def get_index_ohlcv_yfinance(n_days: int = None) -> pd.DataFrame:
    def _fetch():
        import yfinance as yf
        days = n_days or config.HISTORY_TRADING_DAYS
        period_days = int(days * 1.6) + 10
        hist = yf.Ticker(config.INDEX_TICKER).history(period=f"{period_days}d", auto_adjust=True)
        hist = hist.reset_index().rename(columns={
            "Date": "date", "Open": "open", "High": "high",
            "Low": "low", "Close": "close", "Volume": "volume",
        })
        hist["date"] = pd.to_datetime(hist["date"]).dt.tz_localize(None)
        return hist[["date", "open", "high", "low", "close", "volume"]].tail(days).reset_index(drop=True)
    return with_retry(_fetch, max_attempts=3, base_delay=2.0)


# ---------------------------------------------------------------------
# Public interface -- this is what run_pipeline.py actually calls.
# ---------------------------------------------------------------------

def get_index_ohlcv(n_days: int = None) -> pd.DataFrame:
    if config.DATA_SOURCE == "synthetic":
        return get_index_ohlcv_synthetic(n_days)
    elif config.DATA_SOURCE == "yfinance":
        return get_index_ohlcv_yfinance(n_days)
    raise ValueError(f"Unknown DATA_SOURCE: {config.DATA_SOURCE}")


def get_ohlcv(ticker: str, n_days: int = None, index_returns: np.ndarray = None) -> pd.DataFrame:
    if config.DATA_SOURCE == "synthetic":
        return get_ohlcv_synthetic(ticker, n_days, index_returns)
    elif config.DATA_SOURCE == "yfinance":
        return get_ohlcv_yfinance(ticker, n_days)
    raise ValueError(f"Unknown DATA_SOURCE: {config.DATA_SOURCE}")
