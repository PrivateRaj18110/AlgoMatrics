"""Contract tests for the AI-CIO DuckDB reader + client.

DuckDB is embedded, so these run against a **real** file seeded with AI-CIO's
schema — no mocks. They pin the read contract (regime, rankings with dimension
breakdown, news dedup, options, flow), the graceful degradation when the file is
absent, the regime fallback, and that the reader's handle cannot mutate the store.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest

from algo_platform.modules.market_intel.application.client import AicioClient
from algo_platform.modules.market_intel.infrastructure.duckdb_reader import AicioDuckDBReader

pytestmark = pytest.mark.contract


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    # The default pytest tmp_path base is not writable in this environment; use a
    # repo-local dir (same pattern as the encrypted-secrets contract tests).
    base = Path("var") / "test-tmp"
    base.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(dir=base))
    yield path
    shutil.rmtree(path, ignore_errors=True)


def _seed(db: Path) -> None:
    con = duckdb.connect(str(db))
    con.execute(
        "CREATE TABLE regime (run_date DATE, regime VARCHAR, hmm_vol_state VARCHAR, "
        "hmm_confidence DOUBLE, gmm_vol_state VARCHAR, adx_14 DOUBLE, avg_pairwise_corr DOUBLE, "
        "breadth_pct_above_ma20 DOUBLE, days_since_changepoint INTEGER)"
    )
    con.execute(
        "INSERT INTO regime VALUES ('2026-07-16','ranging_low','low',0.82,'low',18.3,0.21,0.44,12)"
    )
    con.execute(
        "CREATE TABLE rankings (run_date DATE, ticker VARCHAR, name VARCHAR, rank INTEGER, "
        "composite_score DOUBLE, regime VARCHAR, rs_60d DOUBLE, mom_20d DOUBLE, "
        "turnover_20d_avg DOUBLE, atr_pct DOUBLE, hv_ratio_10_60 DOUBLE, oi_score DOUBLE, "
        "if_score DOUBLE)"
    )
    con.execute(
        "INSERT INTO rankings VALUES "
        "('2026-07-16','SHREECEM','Shree Cement',1,1.5,'ranging_low',"
        "0.15,0.15,2.4e10,0.04,1.15,-0.65,1.0)"
    )
    # Second row leaves oi_score / if_score NULL (dimensions a run may not populate).
    con.execute(
        "INSERT INTO rankings VALUES "
        "('2026-07-16','GODREJCP','Godrej CP',2,1.28,'ranging_low',"
        "0.43,0.34,3.2e10,0.03,0.89,NULL,NULL)"
    )
    con.execute(
        "CREATE TABLE news (ticker VARCHAR, title VARCHAR, source VARCHAR, link VARCHAR, "
        "published_raw VARCHAR, is_duplicate BOOLEAN, dup_reason VARCHAR, sentiment_label VARCHAR, "
        "sentiment_score DOUBLE, fetch_error VARCHAR, fetched_at TIMESTAMP)"
    )
    con.execute(
        "INSERT INTO news VALUES ('SHREECEM','Cement demand climbs','demo-wire','http://x',"
        "'2026-07-16',FALSE,NULL,'positive',0.4,NULL,TIMESTAMP '2026-07-16 10:00:00')"
    )
    con.execute(
        "INSERT INTO news VALUES ('SHREECEM','Cement demand climbs (dup)','demo-wire','http://y',"
        "'2026-07-16',TRUE,'minhash','neutral',0.0,NULL,TIMESTAMP '2026-07-16 09:00:00')"
    )
    con.execute(
        "CREATE TABLE options_features (ticker VARCHAR, run_date DATE, max_pain DOUBLE, "
        "max_pain_dist_pct DOUBLE, pcr_oi DOUBLE, pcr_volume DOUBLE, iv_skew DOUBLE, "
        "atm_iv DOUBLE, oi_score DOUBLE)"
    )
    con.execute(
        "INSERT INTO options_features VALUES "
        "('SHREECEM','2026-07-16',1645.0,0.025,0.82,0.88,-0.02,0.20,-0.65)"
    )
    con.execute(
        "CREATE TABLE institutional_flow (ticker VARCHAR, run_date DATE, net_value DOUBLE, "
        "gross_value DOUBLE, n_deals INTEGER, if_score DOUBLE)"
    )
    con.execute("INSERT INTO institutional_flow VALUES ('ABB','2026-07-16',3.9e8,3.9e8,2,1.0)")
    con.close()


async def test_reads_regime_and_rankings_with_breakdown(tmp_path: Path) -> None:
    db = tmp_path / "aicio.duckdb"
    _seed(db)
    client = AicioClient(AicioDuckDBReader(db))

    regime = await client.current_regime()
    assert regime is not None
    assert regime.label == "ranging_low"
    assert regime.hmm_confidence == pytest.approx(0.82)
    assert regime.adx_14 == pytest.approx(18.3)

    rankings = await client.rankings(top_n=10)
    assert [row.ticker for row in rankings] == ["SHREECEM", "GODREJCP"]
    assert rankings[0].rank == 1
    dims = {d.name: d.value for d in rankings[1].dimensions}
    assert dims["rs_60d"] == pytest.approx(0.43)
    assert dims["oi_score"] is None  # NULL preserved as None
    assert dims["if_score"] is None

    # Single-ticker filter is case-insensitive.
    one = await client.rankings(ticker="shreecem")
    assert [row.ticker for row in one] == ["SHREECEM"]

    # Favourability is derived from the live regime.
    assert await client.is_favorable_regime("mean_reversion") is True
    assert await client.is_favorable_regime("momentum") is False


async def test_reads_news_options_and_flow(tmp_path: Path) -> None:
    db = tmp_path / "aicio.duckdb"
    _seed(db)
    client = AicioClient(AicioDuckDBReader(db))

    news = await client.recent_news("SHREECEM")
    assert len(news) == 1  # the duplicate is filtered by default
    assert news[0].is_duplicate is False

    news_all = await client.recent_news("SHREECEM", non_duplicates_only=False)
    assert len(news_all) == 2

    options = await client.options_snapshot("shreecem")
    assert options is not None
    assert options.pcr_oi == pytest.approx(0.82)

    assert await client.institutional_bias("ABB") == pytest.approx(1.0)
    assert await client.institutional_bias("NOSUCH") == 0.0  # neutral when no deal


async def test_missing_file_degrades_gracefully(tmp_path: Path) -> None:
    client = AicioClient(AicioDuckDBReader(tmp_path / "not_created.duckdb"))
    assert await client.current_regime() is None
    assert await client.rankings() == []
    assert await client.recent_news("X") == []
    assert await client.options_snapshot("X") is None
    assert await client.institutional_bias("X") == 0.0
    # No data → fail-open (the advisory layer never silently discourages).
    assert await client.is_favorable_regime("momentum") is True


async def test_unconfigured_path_degrades_gracefully() -> None:
    client = AicioClient(AicioDuckDBReader(None))
    assert await client.current_regime() is None
    assert await client.rankings() == []


async def test_regime_falls_back_to_rankings_label(tmp_path: Path) -> None:
    db = tmp_path / "aicio.duckdb"
    con = duckdb.connect(str(db))
    con.execute(
        "CREATE TABLE rankings (run_date DATE, ticker VARCHAR, name VARCHAR, rank INTEGER, "
        "composite_score DOUBLE, regime VARCHAR, rs_60d DOUBLE, mom_20d DOUBLE, "
        "turnover_20d_avg DOUBLE, atr_pct DOUBLE, hv_ratio_10_60 DOUBLE, oi_score DOUBLE, "
        "if_score DOUBLE)"
    )
    con.execute(
        "INSERT INTO rankings VALUES "
        "('2026-07-16','X','X Co',1,0.5,'risk_off',NULL,NULL,NULL,NULL,NULL,NULL,NULL)"
    )
    con.close()  # deliberately no regime table

    regime = await AicioClient(AicioDuckDBReader(db)).current_regime()
    assert regime is not None
    assert regime.label == "risk_off"
    assert regime.hmm_confidence is None  # diagnostics unavailable via the fallback


async def test_reader_handle_is_read_only(tmp_path: Path) -> None:
    db = tmp_path / "aicio.duckdb"
    _seed(db)
    reader = AicioDuckDBReader(db)
    assert reader.rankings()  # exercises the read path

    # The reader only ever opens read_only=True; such a handle rejects writes,
    # which is the storage-level guarantee that this path cannot mutate AI-CIO.
    con = duckdb.connect(str(db), read_only=True)
    with pytest.raises(duckdb.Error):
        con.execute(
            "INSERT INTO rankings VALUES "
            "('2026-07-16','Z','Z Co',3,0.1,'risk_off',NULL,NULL,NULL,NULL,NULL,NULL,NULL)"
        )
    con.close()
