"""Scheduler process: periodic platform jobs.

Runs billing lifecycle rollovers (trial expiry, period end, past-due
fallback) and identity hygiene (expired e-mail tokens, stale sessions).
Jobs emit commands/state changes; they never execute trading logic.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from datetime import timedelta

import structlog
from sqlalchemy import delete, update

from algo_platform.config import get_settings
from algo_platform.modules.billing.application.service import SubscriptionService
from algo_platform.modules.identity.infrastructure.models import (
    EmailTokenModel,
    RefreshTokenModel,
)
from algo_platform.shared.domain.types import utc_now
from algo_platform.shared.infrastructure.database import (
    create_engine,
    create_session_factory,
)
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
    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)
    logger.info("scheduler.started", interval=settings.scheduler_interval_seconds)
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
            await redis.set_str(HEARTBEAT_KEY, utc_now().isoformat(), ttl_seconds=300)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(
                    stop_event.wait(), timeout=settings.scheduler_interval_seconds
                )
    finally:
        await redis.close()
        await engine.dispose()
        logger.info("scheduler.stopped")


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
