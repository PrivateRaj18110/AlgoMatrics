"""Worker process: transactional-outbox relay to Redis Streams.

Polls unpublished outbox rows (SELECT ... FOR UPDATE SKIP LOCKED so multiple
workers can run), publishes each event envelope to the durable ``events``
stream plus a per-type pub/sub channel, then marks rows published in the same
transaction. At-least-once delivery; consumers deduplicate by ``event_id``.
"""

from __future__ import annotations

import asyncio
import contextlib
import signal

import structlog

from algo_platform.config import get_settings
from algo_platform.shared.domain.types import utc_now
from algo_platform.shared.infrastructure.database import (
    create_engine,
    create_session_factory,
)
from algo_platform.shared.infrastructure.email import create_email_sender
from algo_platform.shared.infrastructure.email_outbox import (
    fetch_pending_emails,
    mark_email_failed,
    mark_email_sent,
)
from algo_platform.shared.infrastructure.event_bus_factory import build_event_bus
from algo_platform.shared.infrastructure.metrics_events import record_business_event
from algo_platform.shared.infrastructure.metrics_server import start_process_metrics
from algo_platform.shared.infrastructure.outbox import fetch_unpublished, mark_published
from algo_platform.shared.infrastructure.redis_gateway import RedisGateway
from algo_platform.shared.infrastructure.telemetry import configure_logging

logger = structlog.get_logger("worker")

EVENTS_STREAM = "events"
HEARTBEAT_KEY = "hb:worker"


async def run() -> None:
    settings = get_settings()
    configure_logging(level=settings.log_level, env=settings.app_env, service="algo-worker")
    engine = create_engine(settings.database_url, pool_size=4)
    session_factory = create_session_factory(engine)
    redis = RedisGateway.from_url(settings.redis_url)
    email_sender = create_email_sender(settings)
    event_bus = build_event_bus(settings, redis)
    metrics = start_process_metrics(settings, "algo-worker")
    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)
    logger.info("worker.started")
    try:
        while not stop_event.is_set():
            published = 0
            try:
                async with session_factory() as session:
                    rows = await fetch_unpublished(session, limit=200)
                    if rows:
                        for row in rows:
                            envelope = {
                                "event_id": str(row.event_id),
                                "event_type": row.event_type,
                                "schema_version": row.schema_version,
                                "occurred_at": row.occurred_at.isoformat(),
                                "organization_id": str(row.organization_id)
                                if row.organization_id
                                else None,
                                "aggregate": {
                                    "type": row.aggregate_type,
                                    "id": str(row.aggregate_id),
                                },
                                "producer": "outbox-relay",
                                "payload": row.payload,
                                "headers": row.headers,
                            }
                            if row.event_type == "engine.command.v1":
                                await redis.xadd_json(
                                    "engine:commands",
                                    {"command_id": str(row.event_id), **row.payload},
                                )
                                if metrics is not None:
                                    metrics.events_published_total.labels(
                                        stream="engine:commands"
                                    ).inc()
                            else:
                                await event_bus.publish(EVENTS_STREAM, envelope)
                                await redis.publish_json(f"events:{row.event_type}", envelope)
                                if metrics is not None:
                                    metrics.events_published_total.labels(
                                        stream=EVENTS_STREAM
                                    ).inc()
                                    record_business_event(
                                        metrics, row.event_type, row.payload
                                    )
                        await mark_published(session, [r.event_id for r in rows])
                        await session.commit()
                        published = len(rows)
            except Exception:
                logger.exception("worker.relay_failed")
                await asyncio.sleep(2)
            if published:
                logger.info("worker.relayed", count=published)
            delivered = 0
            try:
                async with session_factory() as session:
                    emails = await fetch_pending_emails(session)
                    for email in emails:
                        try:
                            await email_sender.send(email.message())
                        except Exception as exc:
                            mark_email_failed(email, exc)
                            logger.exception(
                                "worker.email_delivery_failed",
                                email_id=str(email.id),
                                attempt=email.attempts,
                            )
                        else:
                            mark_email_sent(email)
                            delivered += 1
                    await session.commit()
            except Exception:
                logger.exception("worker.email_outbox_failed")
                await asyncio.sleep(2)
            if delivered:
                logger.info("worker.emails_delivered", count=delivered)
            await redis.set_str(HEARTBEAT_KEY, utc_now().isoformat(), ttl_seconds=120)
            if published == 0 and delivered == 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop_event.wait(), timeout=settings.outbox_poll_seconds)
    finally:
        await redis.close()
        await engine.dispose()
        logger.info("worker.stopped")


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
