"""Outbox relay role: publish transactional-outbox events to the event bus.

Extracted verbatim from the original single worker loop. Polls unpublished
outbox rows, publishes each envelope to the durable ``events`` stream (engine
commands go to ``engine:commands``), and marks rows published in the same
transaction. At-least-once; consumers deduplicate by ``event_id``.
"""

from __future__ import annotations

import asyncio
import contextlib

import structlog

from algo_platform.processes.workers.base import WorkerContext
from algo_platform.shared.domain.types import utc_now
from algo_platform.shared.infrastructure.metrics_events import record_business_event
from algo_platform.shared.infrastructure.outbox import fetch_unpublished, mark_published

logger = structlog.get_logger("worker.relay")

EVENTS_STREAM = "events"
HEARTBEAT_KEY = "hb:relay"


class OutboxRelayWorker:
    name = "relay"

    def __init__(self, ctx: WorkerContext) -> None:
        self._ctx = ctx

    async def run(self, stop: asyncio.Event) -> None:
        ctx = self._ctx
        while not stop.is_set():
            published = 0
            try:
                async with ctx.session_factory() as session:
                    rows = await fetch_unpublished(session, limit=200)
                    for row in rows:
                        envelope = {
                            "event_id": str(row.event_id),
                            "event_type": row.event_type,
                            "schema_version": row.schema_version,
                            "occurred_at": row.occurred_at.isoformat(),
                            "organization_id": (
                                str(row.organization_id) if row.organization_id else None
                            ),
                            "aggregate": {
                                "type": row.aggregate_type,
                                "id": str(row.aggregate_id),
                            },
                            "producer": "outbox-relay",
                            "payload": row.payload,
                            "headers": row.headers,
                        }
                        if row.event_type == "engine.command.v1":
                            await ctx.redis.xadd_json(
                                "engine:commands",
                                {"command_id": str(row.event_id), **row.payload},
                            )
                            if ctx.metrics is not None:
                                ctx.metrics.events_published_total.labels(
                                    stream="engine:commands"
                                ).inc()
                        else:
                            await ctx.event_bus.publish(EVENTS_STREAM, envelope)
                            await ctx.redis.publish_json(f"events:{row.event_type}", envelope)
                            if ctx.metrics is not None:
                                ctx.metrics.events_published_total.labels(
                                    stream=EVENTS_STREAM
                                ).inc()
                                record_business_event(ctx.metrics, row.event_type, row.payload)
                    if rows:
                        await mark_published(session, [r.event_id for r in rows])
                        await session.commit()
                        published = len(rows)
            except Exception:
                logger.exception("relay.failed")
                await asyncio.sleep(2)
            if published:
                logger.info("relay.relayed", count=published)
            await ctx.redis.set_str(HEARTBEAT_KEY, utc_now().isoformat(), ttl_seconds=120)
            if published == 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=ctx.settings.outbox_poll_seconds)
