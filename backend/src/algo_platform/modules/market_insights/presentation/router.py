from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query

from algo_platform.api.dependencies.auth import CurrentUserDep, PlatformAdminDep
from algo_platform.api.dependencies.core import SessionDep
from algo_platform.modules.market_insights.application.service import MarketInsightsService
from algo_platform.modules.market_insights.infrastructure.nse_client import NseUnavailable
from algo_platform.shared.domain.errors import UnavailableError

router = APIRouter(tags=["market-insights"])


def _service(session: SessionDep) -> MarketInsightsService:
    return MarketInsightsService(session)


ServiceDep = Annotated[MarketInsightsService, Depends(_service)]


@router.get("/markets/fo-heatmap")
async def fo_heatmap(user: CurrentUserDep, service: ServiceDep) -> dict[str, Any]:
    """Every NSE F&O stock with a delayed quote, sector and market cap."""
    return await service.fo_heatmap()


@router.get("/markets/premarket")
async def premarket(
    user: CurrentUserDep,
    service: ServiceDep,
    trade_date: Annotated[date | None, Query(alias="date")] = None,
) -> dict[str, Any]:
    """The stored NSE pre-open snapshot for a date (latest by default) + screens."""
    result = await service.premarket(trade_date)
    result["dates"] = await service.premarket_dates()
    return result


@router.get("/markets/pulse")
async def pulse(user: CurrentUserDep, service: ServiceDep) -> dict[str, Any]:
    """Indices, global cues, breadth, sectors, regimes and institutional flows."""
    return await service.pulse()


@router.post("/admin/markets/refresh")
async def refresh(
    admin: PlatformAdminDep,
    service: ServiceDep,
    kind: Annotated[Literal["preopen", "fii_dii"], Query()] = "preopen",
) -> dict[str, Any]:
    """Fetch an NSE snapshot now instead of waiting for the scheduler."""
    try:
        if kind == "preopen":
            snapshot = await service.refresh_preopen()
            return {
                "kind": kind,
                "trade_date": str(snapshot.trade_date),
                "rows": len(snapshot.stocks),
            }
        flow = await service.refresh_fii_dii()
        return {"kind": kind, "trade_date": flow.trade_date if flow else None}
    except NseUnavailable as error:
        raise UnavailableError(f"NSE did not answer: {error}") from error
