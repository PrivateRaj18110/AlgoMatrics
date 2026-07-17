"""
Regime engine v2 -- a real ensemble instead of the v0.1 rule-based
placeholder, now that Phase 1 actually has OHLCV for the full 176-stock
universe (not just the index) to compute cross-sectional signals from.

Ensemble members, matching the doc's Part 7 recommended architecture:
  1. HMM (3-state, GaussianHMM) on index log returns -- primary vol
     detector, has real temporal structure (a transition matrix).
  2. GMM (3-component) on rolling (mean, vol) pairs -- secondary,
     complementary detector with no temporal memory, per the doc's
     stated rationale for including both.
  3. PELT changepoint detection on rolling realised vol -- transition
     alerts, this phase's stand-in for the doc's BOCPD.
  4. Cross-sectional average pairwise correlation + breadth across all
     176 tickers -- the "high-corr risk-on/risk-off" axis. v0.1 could
     not compute this at all (index-only data); v2 can, using the
     analytical shortcut avg_corr ~= avg_cov / avg_var instead of an
     O(n^2) rolling pairwise-correlation matrix.

What "8-state" means here is not a literal reproduction of the doc's
R1-R8 (that labeling embeds trading judgment, not just statistics) --
it's 9 labels covering the same conceptual ground: trend x HMM-vol-state
(6), risk_on / risk_off (2), and recovery_transition (1, fired when the
ensemble itself is unconfident or a changepoint just happened -- not a
7th vol/trend combination).
"""
import warnings

import numpy as np
import pandas as pd
from hmmlearn import hmm
from sklearn.mixture import GaussianMixture
import ruptures as rpt

import features as feat


# ---------------------------------------------------------------------
# 1. HMM vol-state detector
# ---------------------------------------------------------------------

def fit_vol_hmm(log_returns: np.ndarray, n_states: int = 3, random_state: int = 42, n_restarts: int = 8):
    """Multiple random restarts, picking the best-converging FINITE fit.
    Plain best-log-likelihood selection is unsafe here: a degenerate fit
    where one state's variance blows up to absorb a handful of outlier
    days can score as well as, or better than, a genuinely well-separated
    fit -- verified empirically while building this (some seeds landed a
    state with 30x the volatility of the others at a HIGHER likelihood
    than the good fits). Those get filtered out before comparing scores.

    Returns (states, state_probs, transmat), all with state 0 = lowest
    realised vol, state n-1 = highest."""
    X = log_returns.reshape(-1, 1)
    candidates = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for seed in range(random_state, random_state + n_restarts):
            try:
                m = hmm.GaussianHMM(n_components=n_states, covariance_type="diag",
                                     n_iter=300, random_state=seed, tol=1e-6)
                m.fit(X)
                vols = np.sqrt(m.covars_.flatten())
                if vols.min() <= 0 or vols.max() / vols.min() > 15:
                    continue  # degenerate: a state absorbing a few outliers, not a real regime
                candidates.append((m.score(X), m))
            except Exception:
                continue
    if not candidates:
        raise RuntimeError(f"HMM fitting found no non-degenerate {n_states}-state solution in "
                            f"{n_restarts} restarts -- try fewer states or more history")
    model = max(candidates, key=lambda c: c[0])[1]
    order = np.argsort(model.covars_.flatten())  # ascending variance
    label_map = {old: new for new, old in enumerate(order)}
    states = np.array([label_map[s] for s in model.predict(X)])
    probs = model.predict_proba(X)[:, order]
    transmat = model.transmat_[np.ix_(order, order)]
    return states, probs, transmat


# ---------------------------------------------------------------------
# 2. GMM secondary detector -- clusters on (rolling mean, rolling vol)
#    pairs, not on returns directly, so it's genuinely complementary to
#    the HMM rather than a slower version of the same thing.
# ---------------------------------------------------------------------

def fit_return_gmm(returns: pd.Series, window: int = 10, n_components: int = 3, random_state: int = 42):
    roll_mean = returns.rolling(window).mean()
    roll_vol = returns.rolling(window).std()
    X = pd.concat([roll_mean, roll_vol], axis=1).dropna()
    gmm = GaussianMixture(n_components=n_components, covariance_type="full", random_state=random_state)
    gmm.fit(X.values)
    order = np.argsort(gmm.means_[:, 1])  # order components by vol mean, ascending
    label_map = {old: new for new, old in enumerate(order)}
    labels = pd.Series(np.array([label_map[s] for s in gmm.predict(X.values)]), index=X.index)
    return labels.reindex(returns.index)


# ---------------------------------------------------------------------
# 3. Changepoint detection -- PELT on rolling realised vol
# ---------------------------------------------------------------------

def detect_changepoints(vol_series: pd.Series, penalty: float = 6.0) -> list:
    clean = vol_series.dropna()
    if len(clean) < 30:
        return []
    algo = rpt.Pelt(model="rbf", min_size=5).fit(clean.values)
    breakpoints = algo.predict(pen=penalty)
    idx_positions = [b - 1 for b in breakpoints if b - 1 < len(clean)]
    return list(clean.index[idx_positions])


# ---------------------------------------------------------------------
# 4. Cross-sectional correlation + breadth across the full universe.
#    avg_corr via the analytical shortcut: for an equal-weighted
#    portfolio of N assets, Var(portfolio) = avg_var/N + avg_cov*(N-1)/N,
#    so avg_cov (and avg_corr, dividing by avg_var) falls out directly --
#    O(N) instead of an O(N^2) full pairwise rolling-correlation matrix.
# ---------------------------------------------------------------------

def avg_pairwise_correlation(returns_wide: pd.DataFrame, window: int = 20) -> pd.Series:
    n = returns_wide.shape[1]
    port_ret = returns_wide.mean(axis=1)
    var_port = port_ret.rolling(window).var()
    avg_var = returns_wide.rolling(window).var().mean(axis=1)
    avg_cov = (var_port * n**2 - n * avg_var) / (n * (n - 1))
    return (avg_cov / avg_var).clip(-1, 1)


def breadth_pct_above_ma(close_wide: pd.DataFrame, ma_window: int = 20) -> pd.Series:
    ma = close_wide.rolling(ma_window).mean()
    return (close_wide > ma).mean(axis=1)


# ---------------------------------------------------------------------
# Ensemble
# ---------------------------------------------------------------------

VOL_LABELS = {0: "low", 1: "normal", 2: "high"}


def build_regime_table(index_df: pd.DataFrame, returns_wide: pd.DataFrame,
                        close_wide: pd.DataFrame) -> pd.DataFrame:
    """returns_wide, close_wide: date-indexed, one column per ticker,
    across the FULL universe (this is the piece v0.1 could not do).
    Returns a date-indexed DataFrame with one row per trading day."""
    d = index_df.sort_values("date").reset_index(drop=True)
    close = d["close"]
    log_ret = np.log(close / close.shift(1)).fillna(0)

    hmm_states, hmm_probs, hmm_transmat = fit_vol_hmm(log_ret.values)
    gmm_labels = fit_return_gmm(log_ret)
    realised_vol_20d = log_ret.rolling(20).std() * np.sqrt(252)
    realised_vol_20d.index = d["date"]  # so changepoint indices map back to real dates
    changepoints = detect_changepoints(realised_vol_20d)
    adx14 = feat.adx(d["high"], d["low"], close, 14)

    corr_aligned = avg_pairwise_correlation(returns_wide, 20).reindex(d["date"]).values
    breadth_aligned = breadth_pct_above_ma(close_wide, 20).reindex(d["date"]).values
    mkt_dir_20d = (close / close.shift(20) - 1).values

    out = pd.DataFrame({
        "date": d["date"],
        "hmm_vol_state": hmm_states,
        "hmm_confidence": hmm_probs[np.arange(len(hmm_states)), hmm_states],
        "gmm_vol_state": gmm_labels.values,
        "adx_14": adx14.values,
        "avg_pairwise_corr": corr_aligned,
        "breadth_pct_above_ma20": breadth_aligned,
        "mkt_dir_20d": mkt_dir_20d,
    })
    out["days_since_changepoint"] = _days_since(out["date"], changepoints)

    # Self-calibrated low-confidence threshold: what counts as "the model
    # isn't sure" depends on how confident this particular fitted model
    # tends to be. A fixed number (e.g. 0.55) can be right for a cleanly
    # separated 2-state fit and wrong for an overlapping 3-state one --
    # this instead flags the bottom quartile of the model's OWN observed
    # confidence distribution, so it stays meaningful regardless of how
    # sharply separated the underlying states turn out to be.
    conf_floor = out["hmm_confidence"].quantile(0.25)

    def label_row(r):
        in_transition = (r["hmm_confidence"] <= conf_floor) or (r["days_since_changepoint"] <= 3)
        if pd.isna(r["avg_pairwise_corr"]) or pd.isna(r["adx_14"]):
            return np.nan
        if in_transition:
            return "recovery_transition"
        if r["avg_pairwise_corr"] >= 0.55:
            return "risk_off" if r["mkt_dir_20d"] < 0 else "risk_on"
        trend = "trending" if r["adx_14"] >= 25 else "ranging"
        vol = VOL_LABELS[int(r["hmm_vol_state"])]
        return f"{trend}_{vol}"

    out["regime"] = out.apply(label_row, axis=1)
    out.attrs["hmm_transmat"] = hmm_transmat
    return out


def _days_since(dates: pd.Series, event_dates: list) -> pd.Series:
    if not event_dates:
        return pd.Series(9999, index=dates.index)
    event_dates = sorted(event_dates)
    out = []
    for d in dates:
        past = [e for e in event_dates if e <= d]
        out.append((d - past[-1]).days if past else 9999)
    return pd.Series(out, index=dates.index)


def latest_regime(regime_table: pd.DataFrame) -> dict:
    valid = regime_table.dropna(subset=["regime"])
    if valid.empty:
        return {"regime": "unknown", "confidence": 0.0}
    row = valid.iloc[-1]
    return {
        "regime": row["regime"],
        "hmm_vol_state": VOL_LABELS[int(row["hmm_vol_state"])],
        "hmm_confidence": round(float(row["hmm_confidence"]), 3),
        "gmm_vol_state": VOL_LABELS.get(int(row["gmm_vol_state"]), "unknown") if pd.notna(row["gmm_vol_state"]) else "unknown",
        "adx_14": round(float(row["adx_14"]), 1),
        "avg_pairwise_corr": round(float(row["avg_pairwise_corr"]), 3),
        "breadth_pct_above_ma20": round(float(row["breadth_pct_above_ma20"]), 3),
        "days_since_changepoint": int(row["days_since_changepoint"]),
    }
