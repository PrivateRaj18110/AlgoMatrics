"""Generic event-consuming worker role.

Wraps the Phase 6 :class:`StreamConsumer` so each domain worker is just a name,
its own consumer group, the event types it cares about, and a handler. Each
worker has an independent group, so they consume the shared ``events`` stream in
parallel and scale independently. Inbox deduplication makes handling
effectively-once.
"""

from __future__ import annotations

import asyncio
import os
import socket
from collections.abc import Awaitable, Callable

import structlog

from algo_platform.processes.workers.base import WorkerContext
from algo_platform.shared.infrastructure.inbox import RedisInbox
from algo_platform.shared.infrastructure.stream_consumer import StreamConsumer

logger = structlog.get_logger("worker.consumer")

EVENTS_STREAM = "events"

# A handler receives the shared context and the event envelope.
EventHandler = Callable[[WorkerContext, dict[str, object]], Awaitable[None]]


class EventConsumerWorker:
    def __init__(
        self,
        ctx: WorkerContext,
        *,
        name: str,
        group: str,
        handler: EventHandler,
        event_prefixes: tuple[str, ...] | None = None,
    ) -> None:
        self.name = name
        self._ctx = ctx
        self._group = group
        self._handler = handler
        # None means "all events"; otherwise match event_type by prefix.
        self._event_prefixes = event_prefixes

    async def run(self, stop: asyncio.Event) -> None:
        consumer_name = f"{socket.gethostname()}-{os.getpid()}"
        consumer = StreamConsumer(
            self._ctx.event_bus,
            stream=EVENTS_STREAM,
            group=self._group,
            consumer=consumer_name,
            handler=self._on_event,
            dedupe=RedisInbox(self._ctx.redis, ttl_seconds=86_400).claim,
        )
        await consumer.run(stop)

    async def _on_event(self, payload: dict[str, object]) -> None:
        event_type = str(payload.get("event_type", ""))
        if self._event_prefixes is not None and not event_type.startswith(self._event_prefixes):
            return  # not for this worker; acked and skipped
        await self._handler(self._ctx, payload)
        if self._ctx.metrics is not None:
            self._ctx.metrics.events_consumed_total.labels(
                stream=EVENTS_STREAM, outcome="ok"
            ).inc()
