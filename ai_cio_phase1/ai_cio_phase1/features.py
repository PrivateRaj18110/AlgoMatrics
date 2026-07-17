"""
Feature engine -- v0.1 of the doc's 300+ feature universe (Part 22),
scoped to the ~39 features computable from daily OHLCV plus an index
series alone. No options chain, no FII/DII flow, no news needed for any
of these -- that's the honest boundary of what "free daily data" buys
you, and it's already enough for a real first cut at momentum,
volatility, liquidity and technical structure.
"""
import numpy as np
import pandas as pd

EPS = 1e-9


# ---------------------------------------------------------------------
# Indicator building blocks
# ---------------------------------------------------------------------

def true_range(high, low, close):
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low, (high - prev_close).abs(), (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr


def atr(high, low, close, n):
    return true_range(high, low, close).ewm(alpha=1 / n, adjust=False).mean()


def adx(high, low, close, n=14):
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=high.index)
    smoothed_tr = true_range(high, low, close).ewm(alpha=1 / n, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / n, adjust=False).mean() / (smoothed_tr + EPS)
    minus_di = 100 * minus_dm.ewm(alpha=1 / n, adjust=False).mean() / (smoothed_tr + EPS)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di + EPS)
    return dx.ewm(alpha=1 / n, adjust=False).mean()


def rsi(close, n=14):
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / n, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / n, adjust=False).mean()
    rs = avg_gain / (avg_loss + EPS)
    return 100 - 100 / (1 + rs)


def macd_hist(close, fast=12, slow=26, signal=9):
    macd = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    sig = macd.ewm(span=signal, adjust=False).mean()
    return macd - sig


def bollinger(close, n=20, k=2):
    ma = close.rolling(n).mean()
    sd = close.rolling(n).std()
    upper, lower = ma + k * sd, ma - k * sd
    width = (upper - lower) / (ma + EPS)
    pct_b = (close - lower) / (upper - lower + EPS)
    return width, pct_b


def parkinson_vol(high, low, n=20):
    log_hl2 = np.log(high / low) ** 2
    factor = 1 / (4 * np.log(2))
    return np.sqrt(log_hl2.rolling(n).mean() * factor) * np.sqrt(252)


def obv(close, volume):
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


def rolling_max_drawdown(close, n):
    roll_max = close.rolling(n, min_periods=1).max()
    dd = close / roll_max - 1
    return dd.rolling(n).min()


def rolling_beta(stock_ret, index_ret, n):
    cov = stock_ret.rolling(n).cov(index_ret)
    var = index_ret.rolling(n).var()
    return cov / (var + EPS)


# ---------------------------------------------------------------------
# Full feature set for one ticker
# ---------------------------------------------------------------------

def compute_features(df: pd.DataFrame, index_df: pd.DataFrame) -> pd.DataFrame:
    """df, index_df: [date, open, high, low, close, volume], date-sorted.
    Returns a wide DataFrame indexed by date with one column per feature.
    """
    d = df.sort_values("date").reset_index(drop=True)
    idx = index_df.sort_values("date").set_index("date")["close"]
    idx = idx.reindex(d["date"]).ffill().values

    close, high, low, volume, open_ = d["close"], d["high"], d["low"], d["volume"], d["open"]
    ret = close.pct_change()
    log_ret = np.log(close / close.shift(1))
    index_ret = pd.Series(idx, index=d.index).pct_change()

    f = pd.DataFrame(index=d.index)
    f["date"] = d["date"]

    # -- Price & return ---------------------------------------------------
    for w in (5, 10, 20, 63, 126, 252):
        f[f"log_ret_{w}d"] = np.log(close / close.shift(w))
    f["mom_20d"] = f["log_ret_20d"]  # friendly alias used by the ranking engine
    f["ret_skew_20d"] = ret.rolling(20).skew()
    f["ret_kurt_20d"] = ret.rolling(20).kurt()
    f["max_dd_60d"] = rolling_max_drawdown(close, 60)
    f["max_dd_252d"] = rolling_max_drawdown(close, 252)
    f["sharpe_20d"] = (ret.rolling(20).mean() / (ret.rolling(20).std() + EPS)) * np.sqrt(252)
    f["sharpe_60d"] = (ret.rolling(60).mean() / (ret.rolling(60).std() + EPS)) * np.sqrt(252)
    f["gap_pct"] = open_ / close.shift(1) - 1
    f["gap_avg_abs_20d"] = f["gap_pct"].abs().rolling(20).mean()
    f["beta_60d"] = rolling_beta(ret, index_ret, 60)
    f["rs_20d"] = (close / close.shift(20) - 1) - (pd.Series(idx, index=d.index) / pd.Series(idx, index=d.index).shift(20) - 1)
    f["rs_60d"] = (close / close.shift(60) - 1) - (pd.Series(idx, index=d.index) / pd.Series(idx, index=d.index).shift(60) - 1)

    # -- Volatility ---------------------------------------------------------
    f["atr_14"] = atr(high, low, close, 14)
    f["atr_pct"] = f["atr_14"] / (close + EPS)
    for w in (10, 20, 60):
        f[f"hv_{w}d"] = log_ret.rolling(w).std() * np.sqrt(252)
    f["hv_ratio_10_60"] = f["hv_10d"] / (f["hv_60d"] + EPS)
    f["parkinson_20d"] = parkinson_vol(high, low, 20)

    # -- Volume & liquidity --------------------------------------------------
    f["turnover_inr"] = close * volume
    f["turnover_20d_avg"] = f["turnover_inr"].rolling(20).mean()
    f["vol_ratio_20d"] = volume / (volume.rolling(20).mean() + EPS)
    f["vol_trend_5_20"] = volume.rolling(5).mean() / (volume.rolling(20).mean() + EPS)

    # -- Technical -------------------------------------------------------
    f["rsi_14"] = rsi(close, 14)
    f["rsi_7"] = rsi(close, 7)
    f["macd_hist"] = macd_hist(close)
    bb_width, bb_pctb = bollinger(close, 20)
    f["bb_width_20d"] = bb_width
    f["bb_pctb_20d"] = bb_pctb
    for w in (20, 50, 200):
        ma = close.rolling(w).mean()
        f[f"dist_from_ma{w}"] = close / (ma + EPS) - 1
    f["pct_from_52w_high"] = close / (close.rolling(252).max() + EPS) - 1
    f["pct_from_52w_low"] = close / (close.rolling(252).min() + EPS) - 1
    above_ma20 = (close > close.rolling(20).mean()).astype(int)
    f["consec_days_above_ma20"] = above_ma20.groupby((above_ma20 != above_ma20.shift()).cumsum()).cumcount() + 1
    f["consec_days_above_ma20"] = f["consec_days_above_ma20"].where(above_ma20 == 1, 0)
    f["obv_mom_10d"] = obv(close, volume).diff(10)
    f["adx_14"] = adx(high, low, close, 14)

    return f
