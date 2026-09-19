"""Scheduler process: periodic platform jobs.

Runs billing lifecycle rollovers (trial expiry, period end, past-due
fallback), identity hygiene (expired e-mail tokens, stale sessions), NSE daily
snapshots and the AI-CIO movers radar (filings, news, forecasts, grading).
Jobs emit commands/state changes; they never execute trading logic.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from datetime import timedelta

import structlog
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from algo_platform.config import Settings, get_settings
from algo_platform.modules.ai.infrastructure.factory import build_llm_provider
from algo_platform.modules.billing.application.service import SubscriptionService
from algo_platform.modules.devices.application.service import DeviceService
from algo_platform.modules.identity.application.directory import UserDirectory
from algo_platform.modules.identity.infrastructure.models import (
    EmailTokenModel,
    RefreshTokenModel,
)
from algo_platform.modules.market_insights.application.briefing import (
    BriefingService,
    briefing_recipients,
)
from algo_platform.modules.market_insights.application.movers import (
    BACKTEST_LOCK_KEY,
    BACKTEST_REQUEST_KEY,
    AlertSink,
    MoversService,
)
from algo_platform.modules.market_insights.application.service import (
    MarketInsightsService,
    ist_now,
)
from algo_platform.modules.market_insights.domain.catalysts import Catalyst, previous_session
from algo_platform.modules.market_insights.infrastructure.ai_reader import ClaudeFilingReader
from algo_platform.modules.market_insights.infrastructure.snapshot_store import SqlSnapshotStore
from algo_platform.modules.notifications.application.service import NotificationService
from algo_platform.modules.organizations.infrastructure.repositories import (
    SqlOrganizationRepository,
)
from algo_platform.shared.domain.types import UserId, utc_now
from algo_platform.shared.infrastructure.database import (
    create_engine,
    create_session_factory,
)
from algo_platform.shared.infrastructure.email_outbox import TransactionalEmailSender
from algo_platform.shared.infrastructure.heartbeats import read_heartbeats
from algo_platform.shared.infrastructure.metrics_server import start_process_metrics
from algo_platform.shared.infrastructure.redis_gateway import RedisGateway
from algo_platform.shared.infrastructure.telemetry import configure_logging

logger = structlog.get_logger("scheduler")

HEARTBEAT_KEY = "hb:scheduler"


async def run() -> None:
    settings = get_settings()
    configure_logging(level=settings.log_level, env=settings.app_env, service="algo-scheduler")
    engine = create_engine(settings.database_url, pool_size=4)
    session_factory = create_session_factory(engine)
    redis = RedisGateway.from_url(settings.redis_url)
    start_process_metrics(settings, "algo-scheduler")
    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)
    logger.info("scheduler.started", interval=settings.scheduler_interval_seconds)
    reader = _filing_reader(settings)
    backtest: asyncio.Task[None] | None = None
    try:
        while not stop_event.is_set():
            try:
                async with session_factory() as session:
                    billing = SubscriptionService(
                        session=session,
                        providers={},
                        app_base_url=settings.app_base_url,
                        notifications=None,
                    )
                    rolled = await billing.run_lifecycle_tick()
                    if rolled:
                        logger.info("scheduler.subscriptions_rolled", count=rolled)

                    now = utc_now()
                    await session.execute(
                        delete(EmailTokenModel).where(
                            EmailTokenModel.expires_at < now - timedelta(days=7)
                        )
                    )
                    await session.execute(
                        update(RefreshTokenModel)
                        .where(
                            RefreshTokenModel.expires_at < now,
                            RefreshTokenModel.revoked_at.is_(None),
                        )
                        .values(revoked_at=now)
                    )
                    await session.commit()
            except Exception:
                logger.exception("scheduler.tick_failed")
            # NSE daily snapshots (pre-open ~09:08 IST, FII/DII in the evening).
            # Separate transaction: a market-data hiccup must not undo billing work.
            try:
                async with session_factory() as session:
                    await MarketInsightsService(session).scheduled_tick(redis)
                    # Device trades/logs/alerts are kept for 30 days; pruning hourly is plenty.
                    if utc_now().minute == 0:
                        await DeviceService(session).prune()
                    await session.commit()
            except Exception:
                logger.exception("scheduler.market_tick_failed")
            # AI-CIO movers radar. Own transaction; the one-off backtest runs in the
            # background so the loop (and its heartbeat) keeps going meanwhile.
            try:
                async with session_factory() as session:
                    movers = MoversService(SqlSnapshotStore(session), reader=reader)
                    await movers.scheduled_tick(redis, alert=_catalyst_alerts(session, redis))
                    await session.commit()
                    requested = await redis.get_str(BACKTEST_REQUEST_KEY) is not None
                    idle = backtest is None or backtest.done()
                    if (
                        idle
                        and (requested or await movers.backtest_needed())
                        and await redis.set_if_absent(BACKTEST_LOCK_KEY, ttl_seconds=3 * 3600)
                    ):
                        await redis.delete(BACKTEST_REQUEST_KEY)
                        backtest = asyncio.create_task(
                            _run_backtest(session_factory, redis, reader)
                        )
            except Exception:
                logger.exception("scheduler.movers_tick_failed")
            # AI-CIO morning briefing (~09:10 IST), queued in the e-mail outbox.
            if settings.daily_briefing_enabled:
                try:
                    async with session_factory() as session:
                        await _maybe_send_briefing(session, redis, settings)
                        await session.commit()
                except Exception:
                    logger.exception("scheduler.briefing_failed")
            await redis.set_str(HEARTBEAT_KEY, utc_now().isoformat(), ttl_seconds=300)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(
                    stop_event.wait(), timeout=settings.scheduler_interval_seconds
                )
    finally:
        if backtest is not None and not backtest.done():
            backtest.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await backtest
        await redis.close()
        await engine.dispose()
        logger.info("scheduler.stopped")


def _filing_reader(settings: Settings) -> ClaudeFilingReader | None:
    """Claude reads material filings only when the AI provider is configured."""
    if settings.ai_provider != "anthropic" or not settings.anthropic_api_key:
        return None
    provider = build_llm_provider(
        settings.model_copy(update={"ai_model": settings.market_ai_model})
    )
    return ClaudeFilingReader(provider)


def _catalyst_alerts(session: AsyncSession, redis: RedisGateway) -> AlertSink:
    """In-app alert to each platform owner (their first organisation) per filing."""

    async def send(items: list[Catalyst]) -> None:
        notifications = NotificationService(session, redis)
        organizations = SqlOrganizationRepository(session)
        for user_id in await UserDirectory(session).platform_admin_ids():
            memberships = await organizations.list_for_user(UserId(user_id))
            if not memberships:
                continue
            organization = memberships[0][0]
            for item in items:
                mark = "▲ " if item.direction > 0 else "▼ " if item.direction < 0 else ""
                await notifications.notify(
                    organization_id=organization.id,
                    user_id=user_id,
                    title=f"{item.symbol}: {item.label}"[:140],
                    body=f"{mark}{item.title}"[:400],
                    type_="market",
                    severity="warning" if item.impact >= 0.75 else "info",
                    payload={
                        "symbol": item.symbol,
                        "catalyst_id": item.id,
                        "url": item.url,
                        "link": "/app/market-intelligence",
                    },
                )

    return send


async def _maybe_send_briefing(
    session: AsyncSession, redis: RedisGateway, settings: Settings
) -> None:
    store = SqlSnapshotStore(session)
    briefing = BriefingService(store, MoversService(store))
    now = ist_now()
    if not await briefing.due(now):
        return
    # One sender per morning even with several scheduler replicas.
    if not await redis.set_if_absent(f"mv:briefing:lock:{now.date().isoformat()}", ttl_seconds=600):
        return
    alerts = await redis.get_str(f"mv:alerts:{previous_session(now.date()).isoformat()}")
    result = await briefing.send(
        now.date(),
        recipients=briefing_recipients(
            await UserDirectory(session).platform_admin_emails(), settings.daily_briefing_recipients
        ),
        sender=TransactionalEmailSender(session),
        heartbeats=await read_heartbeats(redis, settings),
        alerts_yesterday=int(alerts or 0),
        delivery=settings.email_backend,
        console_url=settings.app_base_url,
    )
    logger.info(
        "scheduler.briefing_queued", recipients=len(result["recipients"]), stage=result["stage"]
    )


async def _run_backtest(
    session_factory: async_sessionmaker[AsyncSession],
    redis: RedisGateway,
    reader: ClaudeFilingReader | None,
) -> None:
    try:
        async with session_factory() as session:
            report = await MoversService(SqlSnapshotStore(session), reader=reader).backtest()
            await session.commit()
        logger.info(
            "scheduler.movers_backtest_done",
            sessions=report.get("sessions"),
            filings=report.get("filings"),
        )
    except Exception:
        logger.exception("scheduler.movers_backtest_failed")
    finally:
        await redis.delete(BACKTEST_LOCK_KEY)


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_event_loop()
    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_: stop_event.set())


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
