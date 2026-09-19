from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query

from algo_platform.api.dependencies.auth import CurrentUserDep, PlatformAdminDep
from algo_platform.api.dependencies.core import RedisDep, SessionDep, SettingsDep
from algo_platform.modules.identity.application.directory import UserDirectory
from algo_platform.modules.market_insights.application.briefing import (
    BriefingService,
    briefing_recipients,
)
from algo_platform.modules.market_insights.application.movers import (
    BACKTEST_LOCK_KEY,
    BACKTEST_REQUEST_KEY,
    MoversService,
)
from algo_platform.modules.market_insights.application.service import (
    MarketInsightsService,
    ist_now,
)
from algo_platform.modules.market_insights.infrastructure.nse_client import NseUnavailable
from algo_platform.modules.market_insights.infrastructure.snapshot_store import SqlSnapshotStore
from algo_platform.shared.domain.errors import UnavailableError
from algo_platform.shared.infrastructure.email_outbox import TransactionalEmailSender
from algo_platform.shared.infrastructure.heartbeats import read_heartbeats

router = APIRouter(tags=["market-insights"])


def _service(session: SessionDep) -> MarketInsightsService:
    return MarketInsightsService(session)


ServiceDep = Annotated[MarketInsightsService, Depends(_service)]


def _movers(session: SessionDep) -> MoversService:
    return MoversService(SqlSnapshotStore(session))


MoversDep = Annotated[MoversService, Depends(_movers)]
DateQuery = Annotated[date | None, Query(alias="date")]


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


@router.get("/markets/movers")
async def movers(
    user: CurrentUserDep, service: MoversDep, trade_date: DateQuery = None
) -> dict[str, Any]:
    """AI-CIO: today's (or a past date's) major-move forecast, with reasons and the grade."""
    return await service.movers(trade_date)


@router.get("/markets/movers/track-record")
async def movers_track_record(user: CurrentUserDep, service: MoversDep) -> dict[str, Any]:
    """How the forecasts have done live and in the backtest, plus the model's weights."""
    return await service.track_record()


@router.get("/markets/catalysts")
async def catalysts(
    user: CurrentUserDep,
    service: MoversDep,
    trade_date: DateQuery = None,
    min_impact: Annotated[float, Query(ge=0, le=1)] = 0.15,
) -> dict[str, Any]:
    """Classified NSE filings and exchange events for the F&O universe."""
    return await service.catalysts(trade_date, min_impact=min_impact)


@router.get("/markets/news")
async def news(
    user: CurrentUserDep,
    service: MoversDep,
    trade_date: DateQuery = None,
    tagged: bool = False,
) -> dict[str, Any]:
    """Market headlines since the last close, tagged with the F&O stocks they mention."""
    return await service.news(trade_date, tagged_only=tagged)


MoversJob = Literal["filings", "events", "news", "forecast", "grade", "backtest"]


@router.post("/admin/markets/movers")
async def run_movers_job(
    admin: PlatformAdminDep,
    service: MoversDep,
    redis: RedisDep,
    job: Annotated[MoversJob, Query()] = "forecast",
) -> dict[str, Any]:
    """Run one AI-CIO step now instead of waiting for the scheduler."""
    today = ist_now().date()
    try:
        if job == "filings":
            return {"job": job, "new": len(await service.collect_filings(today))}
        if job == "events":
            payload = await service.collect_events(today)
            return {"job": job, "events": sum(len(v) for v in payload["by_source"].values())}
        if job == "news":
            return {"job": job, "headlines": await service.collect_news(today)}
        if job == "forecast":
            built = [
                stage
                for stage in ("overnight", "opening")
                if await service.build_forecast(today, stage) is not None
            ]
            return {"job": job, "stages": built}
        if job == "grade":
            grades = await service.evaluate(today)
            if grades is not None:
                await service.recalibrate(today)
            return {"job": job, "graded": grades is not None}
    except NseUnavailable as error:
        raise UnavailableError(f"NSE did not answer: {error}") from error
    if await redis.get_str(BACKTEST_LOCK_KEY) is not None:
        return {"job": job, "queued": False, "detail": "a backtest is already running"}
    await redis.set_str(BACKTEST_REQUEST_KEY, "1", ttl_seconds=3600)
    return {"job": job, "queued": True, "detail": "the scheduler starts it within a minute"}


@router.get("/admin/markets/briefing")
async def briefing_archive(
    admin: PlatformAdminDep,
    session: SessionDep,
    settings: SettingsDep,
    trade_date: DateQuery = None,
) -> dict[str, Any]:
    """Stored AI-CIO morning briefings (the daily log), newest first."""
    store = SqlSnapshotStore(session)
    archive = await BriefingService(store, MoversService(store)).archive(trade_date)
    return {
        **archive,
        "delivery": settings.email_backend,
        "enabled": settings.daily_briefing_enabled,
    }


@router.post("/admin/markets/briefing")
async def send_briefing(
    admin: PlatformAdminDep,
    session: SessionDep,
    redis: RedisDep,
    settings: SettingsDep,
    send: bool = False,
) -> dict[str, Any]:
    """Build today's briefing now: a preview, or (``send=true``) e-mail it and log it."""
    store = SqlSnapshotStore(session)
    service = BriefingService(store, MoversService(store))
    today = ist_now().date()
    heartbeats = await read_heartbeats(redis, settings)
    if not send:
        preview = await service.build(
            today,
            heartbeats=heartbeats,
            delivery=settings.email_backend,
            console_url=settings.app_base_url,
        )
        return {
            "day": today.isoformat(),
            "subject": preview.subject,
            "html": preview.html,
            "text": preview.text,
        }
    result = await service.send(
        today,
        recipients=briefing_recipients(
            await UserDirectory(session).platform_admin_emails(), settings.daily_briefing_recipients
        ),
        sender=TransactionalEmailSender(session),
        heartbeats=heartbeats,
        delivery=settings.email_backend,
        console_url=settings.app_base_url,
    )
    return {"day": today.isoformat(), **result}


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
