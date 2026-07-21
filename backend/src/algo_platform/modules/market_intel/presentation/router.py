"""Read-only market-intelligence API: regime, rankings, news, options, flow.

Every endpoint is a projection of the AI-CIO DuckDB — advisory, never a trade
signal. All are gated on ``ANALYTICS_VIEW`` and degrade to ``null``/``[]`` when
AI-CIO is unconfigured or has not produced data yet.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from algo_platform.api.dependencies.core import SettingsDep
from algo_platform.api.dependencies.tenant import TenantContext, require_permission
from algo_platform.config import Settings
from algo_platform.modules.market_intel.application.client import AicioClient
from algo_platform.modules.market_intel.domain.indices import INDEX_GROUPS, symbols_for_index
from algo_platform.modules.market_intel.infrastructure.duckdb_reader import get_aicio_reader
from algo_platform.modules.organizations.domain.roles import Permission

# Whole-universe scan size when filtering rankings to an index subset.
_UNIVERSE_SCAN = 1000

router = APIRouter(prefix="/market-intel", tags=["market-intel"])

MarketIntelTenant = Annotated[TenantContext, Depends(require_permission(Permission.ANALYTICS_VIEW))]


class StatusResponse(BaseModel):
    configured: bool


class IndexGroupResponse(BaseModel):
    value: str
    label: str


class RegimeResponse(BaseModel):
    label: str
    hmm_confidence: float | None
    hmm_vol_state: str | None
    gmm_vol_state: str | None
    adx_14: float | None
    avg_pairwise_corr: float | None
    breadth_pct_above_ma20: float | None
    days_since_changepoint: int | None
    as_of: str | None


class RankingDimensionResponse(BaseModel):
    name: str
    value: float | None


class RankingRowResponse(BaseModel):
    run_date: str
    ticker: str
    name: str | None
    rank: int
    composite_score: float
    regime: str
    dimensions: list[RankingDimensionResponse]


class NewsItemResponse(BaseModel):
    ticker: str
    title: str
    source: str
    link: str
    published_raw: str | None
    is_duplicate: bool
    sentiment_label: str | None
    sentiment_score: float | None


class OptionsSnapshotResponse(BaseModel):
    ticker: str
    run_date: str
    max_pain: float | None
    max_pain_dist_pct: float | None
    pcr_oi: float | None
    pcr_volume: float | None
    iv_skew: float | None
    atm_iv: float | None
    oi_score: float | None


class InstitutionalBiasResponse(BaseModel):
    ticker: str
    run_date: str
    net_value: float | None
    gross_value: float | None
    n_deals: int | None
    if_score: float


def _client(settings: Settings) -> AicioClient:
    return AicioClient(get_aicio_reader(settings.aicio_duckdb_path))


@router.get("/status", response_model=StatusResponse)
async def status(tenant: MarketIntelTenant, settings: SettingsDep) -> StatusResponse:
    """Whether an AI-CIO DuckDB path is configured (not whether it has data)."""
    return StatusResponse(configured=settings.aicio_duckdb_path is not None)


@router.get("/regime", response_model=RegimeResponse | None)
async def regime(tenant: MarketIntelTenant, settings: SettingsDep) -> RegimeResponse | None:
    """Current market regime with ensemble diagnostics, or ``null`` if unavailable."""
    current = await _client(settings).current_regime()
    return RegimeResponse.model_validate(current, from_attributes=True) if current else None


@router.get("/indices", response_model=list[IndexGroupResponse])
async def indices(tenant: MarketIntelTenant, settings: SettingsDep) -> list[IndexGroupResponse]:
    """Index groups the rankings can be filtered by (Nifty 50, Bank Nifty, …)."""
    return [IndexGroupResponse(value=value, label=label) for value, label in INDEX_GROUPS]


@router.get("/rankings", response_model=list[RankingRowResponse])
async def rankings(
    tenant: MarketIntelTenant,
    settings: SettingsDep,
    top_n: Annotated[int, Query(ge=1, le=200)] = 20,
    ticker: Annotated[str | None, Query(description="filter to a single NSE symbol")] = None,
    index: Annotated[
        str | None, Query(description="filter to an index group, e.g. nifty50 / banknifty")
    ] = None,
) -> list[RankingRowResponse]:
    """Top-N ranked opportunities for the latest run, with dimension breakdowns.

    ``index`` restricts the ranking to that index's constituents (top-N within it);
    an unknown index returns an empty list.
    """
    client = _client(settings)
    if index:
        members = symbols_for_index(index)
        if members is None:
            return []
        ranked = await client.rankings(top_n=_UNIVERSE_SCAN)
        rows = [row for row in ranked if row.ticker.upper() in members][:top_n]
    else:
        rows = await client.rankings(top_n=top_n, ticker=ticker)
    return [RankingRowResponse.model_validate(row, from_attributes=True) for row in rows]


@router.get("/news", response_model=list[NewsItemResponse])
async def news(
    tenant: MarketIntelTenant,
    settings: SettingsDep,
    ticker: Annotated[str | None, Query(description="filter to a single NSE symbol")] = None,
    include_duplicates: Annotated[bool, Query()] = False,
) -> list[NewsItemResponse]:
    """Recent deduped headlines with lexicon sentiment; all tickers by default."""
    items = await _client(settings).recent_news(ticker, non_duplicates_only=not include_duplicates)
    return [NewsItemResponse.model_validate(item, from_attributes=True) for item in items]


@router.get("/options/{ticker}", response_model=OptionsSnapshotResponse | None)
async def options(
    ticker: str, tenant: MarketIntelTenant, settings: SettingsDep
) -> OptionsSnapshotResponse | None:
    """PCR / max-pain / IV-skew snapshot for a ticker, or ``null`` if none."""
    snapshot = await _client(settings).options_snapshot(ticker)
    return (
        OptionsSnapshotResponse.model_validate(snapshot, from_attributes=True) if snapshot else None
    )


@router.get("/flow/{ticker}", response_model=InstitutionalBiasResponse | None)
async def flow(
    ticker: str, tenant: MarketIntelTenant, settings: SettingsDep
) -> InstitutionalBiasResponse | None:
    """Bulk/block-deal institutional-flow read for a ticker, or ``null`` if none."""
    bias = await _client(settings).institutional_flow(ticker)
    return InstitutionalBiasResponse.model_validate(bias, from_attributes=True) if bias else None
