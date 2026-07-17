"""
Thin DuckDB wrapper. One local file (config.DB_PATH) holds everything --
no server, no cluster, nothing to provision. This is what "ClickHouse +
Postgres + Redis" collapses into at 250-stock, daily-bar scale.
"""
import duckdb
import pandas as pd

import config

# The rankings table's full column set, in order. save_rankings reindexes any
# incoming frame to exactly these columns (NULL-filling the weighted dimensions
# a given regime/run did not populate) so the INSERT stays stable regardless of
# which dimensions were active that day.
RANKING_COLUMNS = [
    "run_date", "ticker", "name", "rank", "composite_score", "regime",
    "rs_60d", "mom_20d", "turnover_20d_avg", "atr_pct", "hv_ratio_10_60",
    "oi_score", "if_score",
]


class Store:
    def __init__(self, db_path=None):
        self.con = duckdb.connect(str(db_path or config.DB_PATH))
        self._init_schema()

    def _init_schema(self):
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS ohlcv (
                ticker VARCHAR, date DATE, open DOUBLE, high DOUBLE,
                low DOUBLE, close DOUBLE, volume BIGINT
            )
        """)
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS features (
                ticker VARCHAR, date DATE, feature VARCHAR, value DOUBLE
            )
        """)
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS quality_log (
                ticker VARCHAR, run_date DATE, check_name VARCHAR,
                passed BOOLEAN, severity VARCHAR, detail VARCHAR
            )
        """)
        # rankings carries the base score plus the raw weighted dimensions, so a
        # downstream reader can show *why* a ticker ranks where it does without
        # re-deriving anything. The dimension columns are nullable: which are
        # populated depends on the regime's active weights and on whether the
        # options / institutional-flow modules have been run.
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS rankings (
                run_date DATE, ticker VARCHAR, name VARCHAR, rank INTEGER,
                composite_score DOUBLE, regime VARCHAR,
                rs_60d DOUBLE, mom_20d DOUBLE, turnover_20d_avg DOUBLE,
                atr_pct DOUBLE, hv_ratio_10_60 DOUBLE, oi_score DOUBLE, if_score DOUBLE
            )
        """)
        # One row per pipeline run: the regime label plus the ensemble
        # diagnostics latest_regime() surfaces, so a consumer gets confidence
        # and the HMM/GMM/ADX/correlation reads, not just the bare label.
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS regime (
                run_date DATE, regime VARCHAR, hmm_vol_state VARCHAR,
                hmm_confidence DOUBLE, gmm_vol_state VARCHAR, adx_14 DOUBLE,
                avg_pairwise_corr DOUBLE, breadth_pct_above_ma20 DOUBLE,
                days_since_changepoint INTEGER
            )
        """)
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS news (
                ticker VARCHAR, title VARCHAR, source VARCHAR, link VARCHAR,
                published_raw VARCHAR, is_duplicate BOOLEAN, dup_reason VARCHAR,
                sentiment_label VARCHAR, sentiment_score DOUBLE, fetch_error VARCHAR,
                fetched_at TIMESTAMP
            )
        """)
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS options_features (
                ticker VARCHAR, run_date DATE, max_pain DOUBLE, max_pain_dist_pct DOUBLE,
                pcr_oi DOUBLE, pcr_volume DOUBLE, iv_skew DOUBLE, atm_iv DOUBLE, oi_score DOUBLE
            )
        """)
        self.con.execute("""
            CREATE TABLE IF NOT EXISTS institutional_flow (
                ticker VARCHAR, run_date DATE, net_value DOUBLE, gross_value DOUBLE,
                n_deals INTEGER, if_score DOUBLE
            )
        """)

    def _upsert(self, table: str, df: pd.DataFrame, key_cols: list):
        if df.empty:
            return
        view = f"tmp_{table}"
        self.con.register(view, df)
        where = " AND ".join(f"{table}.{c} = {view}.{c}" for c in key_cols)
        self.con.execute(f"DELETE FROM {table} USING {view} WHERE {where}")
        self.con.execute(f"INSERT INTO {table} SELECT * FROM {view}")
        self.con.unregister(view)

    def save_ohlcv(self, df: pd.DataFrame, ticker: str):
        out = df.copy()
        out["ticker"] = ticker
        out = out[["ticker", "date", "open", "high", "low", "close", "volume"]]
        self._upsert("ohlcv", out, ["ticker", "date"])

    def read_ohlcv(self, ticker: str) -> pd.DataFrame:
        return self.con.execute(
            "SELECT * FROM ohlcv WHERE ticker = ? ORDER BY date", [ticker]
        ).df()

    def latest_date(self, ticker: str):
        """Most recent stored bar date for a ticker, or None if we have nothing yet."""
        r = self.con.execute("SELECT max(date) FROM ohlcv WHERE ticker = ?", [ticker]).fetchone()
        return r[0] if r and r[0] is not None else None

    def save_features(self, long_df: pd.DataFrame):
        """long_df columns: ticker, date, feature, value"""
        self._upsert("features", long_df, ["ticker", "date", "feature"])

    def save_quality_log(self, df: pd.DataFrame, run_date):
        self.con.execute("DELETE FROM quality_log WHERE run_date = ?", [run_date])
        self.con.register("tmp_ql", df)
        self.con.execute("INSERT INTO quality_log SELECT * FROM tmp_ql")
        self.con.unregister("tmp_ql")

    def save_rankings(self, df: pd.DataFrame):
        # Reindex to the fixed schema so any dimension a given regime/run did
        # not compute lands as NULL rather than shifting the INSERT's columns.
        out = df.reindex(columns=RANKING_COLUMNS)
        run_dates = out["run_date"].unique().tolist()
        self.con.register("tmp_rk", out)
        for d in run_dates:
            self.con.execute("DELETE FROM rankings WHERE run_date = ?", [d])
        cols = ", ".join(RANKING_COLUMNS)
        self.con.execute(f"INSERT INTO rankings ({cols}) SELECT {cols} FROM tmp_rk")
        self.con.unregister("tmp_rk")

    def latest_rankings(self, n: int = 15) -> pd.DataFrame:
        return self.con.execute(
            "SELECT * FROM rankings WHERE run_date = (SELECT max(run_date) FROM rankings) "
            "ORDER BY rank LIMIT ?", [n]
        ).df()

    def save_regime(self, regime_info: dict, run_date):
        """Persist the latest_regime() dict for one run. Missing keys (the
        degenerate 'unknown' case returns only regime/confidence) store as NULL."""
        row = {
            "run_date": run_date,
            "regime": regime_info.get("regime"),
            "hmm_vol_state": regime_info.get("hmm_vol_state"),
            "hmm_confidence": regime_info.get("hmm_confidence"),
            "gmm_vol_state": regime_info.get("gmm_vol_state"),
            "adx_14": regime_info.get("adx_14"),
            "avg_pairwise_corr": regime_info.get("avg_pairwise_corr"),
            "breadth_pct_above_ma20": regime_info.get("breadth_pct_above_ma20"),
            "days_since_changepoint": regime_info.get("days_since_changepoint"),
        }
        self._upsert("regime", pd.DataFrame([row]), ["run_date"])

    def latest_regime_row(self) -> pd.DataFrame:
        return self.con.execute(
            "SELECT * FROM regime WHERE run_date = (SELECT max(run_date) FROM regime)"
        ).df()

    def save_news(self, df: pd.DataFrame):
        if df.empty:
            return
        out = df.copy()
        out["fetched_at"] = pd.Timestamp.now()
        self.con.register("tmp_news", out)
        self.con.execute("INSERT INTO news SELECT * FROM tmp_news")
        self.con.unregister("tmp_news")

    def read_news(self, ticker: str = None, non_duplicates_only: bool = True) -> pd.DataFrame:
        q = "SELECT * FROM news WHERE 1=1"
        params = []
        if ticker:
            q += " AND ticker = ?"
            params.append(ticker)
        if non_duplicates_only:
            q += " AND is_duplicate = FALSE"
        return self.con.execute(q, params).df()

    def save_options_features(self, df: pd.DataFrame, run_date):
        if df.empty:
            return
        out = df.copy()
        out["run_date"] = run_date
        cols = ["ticker", "run_date", "max_pain", "max_pain_dist_pct", "pcr_oi",
                "pcr_volume", "iv_skew", "atm_iv", "oi_score"]
        out = out.reindex(columns=cols)
        self._upsert("options_features", out, ["ticker", "run_date"])

    def save_institutional_flow(self, df: pd.DataFrame, run_date):
        if df.empty:
            return
        out = df.copy()
        out["run_date"] = run_date
        cols = ["ticker", "run_date", "net_value", "gross_value", "n_deals", "if_score"]
        out = out.reindex(columns=cols)
        self._upsert("institutional_flow", out, ["ticker", "run_date"])

    def latest_options_features(self) -> pd.DataFrame:
        return self.con.execute(
            "SELECT * FROM options_features WHERE run_date = (SELECT max(run_date) FROM options_features)"
        ).df()

    def latest_institutional_flow(self) -> pd.DataFrame:
        return self.con.execute(
            "SELECT * FROM institutional_flow WHERE run_date = (SELECT max(run_date) FROM institutional_flow)"
        ).df()

    def close(self):
        self.con.close()


def merge_ohlcv(existing: pd.DataFrame, new: pd.DataFrame, max_days: int = None) -> pd.DataFrame:
    """Combine previously-stored bars with freshly fetched ones for an
    incremental update. Dedupes on date (new wins, in case a broker
    revises today's still-forming bar), keeps it sorted, and trims to
    max_days if given so history doesn't grow unbounded run over run."""
    if existing.empty:
        combined = new.copy()
    elif new.empty:
        combined = existing.copy()
    else:
        combined = pd.concat([existing, new], ignore_index=True)
    combined = combined.drop_duplicates(subset="date", keep="last").sort_values("date").reset_index(drop=True)
    if max_days:
        combined = combined.tail(max_days).reset_index(drop=True)
    return combined
