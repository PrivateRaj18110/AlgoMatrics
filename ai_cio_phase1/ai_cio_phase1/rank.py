"""
Ranking engine -- v0.1 of the doc's Part 8 composite Opportunity Score.
Only RS, a momentum term, liquidity, and two volatility terms are
included, because those are the only dimensions this phase actually has
data for. IF (institutional flow), NE (news/event), OI (options) plug in
as additional weighted z-scores the moment those modules exist --
nothing else in this file needs to change.
"""
import numpy as np
import pandas as pd

import config


def _zscore(s: pd.Series) -> pd.Series:
    mu, sd = s.mean(), s.std()
    if not sd or np.isnan(sd):
        return pd.Series(0.0, index=s.index)
    z = (s - mu) / sd
    return z.fillna(0.0)  # a ticker missing just THIS dimension gets a neutral
                           # contribution on it, not exclusion from the ranking


def rank_universe(latest_features: pd.DataFrame, universe: pd.DataFrame, regime: str, run_date) -> pd.DataFrame:
    """latest_features: one row per ticker, columns = feature names + 'ticker'.
    Extra dimensions (oi_score, if_score) are optional -- if a column is
    entirely absent (that module hasn't been run yet) its weight is
    dropped and the remaining weights renormalise to sum to 1, so this
    degrades gracefully instead of crashing.

    Returns ranked DataFrame: run_date, ticker, name, rank, composite_score, regime,
    plus the raw inputs for transparency.
    """
    weights = dict(config.REGIME_WEIGHTS.get(regime, config.DEFAULT_WEIGHTS))
    df = latest_features.merge(universe[["ticker", "name"]], on="ticker", how="left")

    available = {k: w for k, w in weights.items() if k in df.columns}
    dropped = set(weights) - set(available)
    if dropped:
        total = sum(available.values())
        available = {k: w / total for k, w in available.items()} if total else available
    weights = available

    z_components = {k: _zscore(df[k]) for k in weights}
    score = sum(weights[k] * z_components[k] for k in weights)
    df["composite_score"] = score
    df["run_date"] = run_date
    df["regime"] = regime

    df = df.sort_values("composite_score", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1

    cols = ["run_date", "ticker", "name", "rank", "composite_score", "regime"] + list(weights)
    return df[cols]
