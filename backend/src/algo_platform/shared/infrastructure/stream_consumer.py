"""Reusable consumer-group runner over the abstract :class:`EventBus`.

Encapsulates the delivery loop that would otherwise be duplicated per consumer:
recover stale/pending messages, read new ones, invoke a handler, acknowledge on
success, and dead-letter a message that fails repeatedly (poison). Optional inbox
deduplication skips events already processed (at-least-once → effectively-once).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import defaultdict
from collections.abc import Awaitable, Callable

import structlog

from algo_platform.shared.application.event_bus import EventBus, StreamMessage

logger = structlog.get_logger("stream_consumer")

Handler = Callable[[dict[str, object]], Awaitable[None]]
# Returns True if this event id has NOT been processed before (i.e. proceed).
DedupeCheck = Callable[[str], Awaitable[bool]]


class StreamConsumer:
    def __init__(
        self,
        bus: EventBus,
        *,
        stream: str,
        group: str,
        consumer: str,
        handler: Handler,
        max_attempts: int = 5,
        batch: int = 50,
        block_ms: int = 2000,
        reclaim_idle_ms: int = 30_000,
        dedupe: DedupeCheck | None = None,
        id_field: str = "event_id",
    ) -> None:
        self._bus = bus
        self._stream = stream
        self._group = group
        self._consumer = consumer
        self._handler = handler
        self._max_attempts = max_attempts
        self._batch = batch
        self._block_ms = block_ms
        self._reclaim_idle_ms = reclaim_idle_ms
        self._dedupe = dedupe
        self._id_field = id_field
        self._attempts: dict[str, int] = defaultdict(int)

    async def poll_once(self) -> int:
        """Recover stale messages or read new ones and process them once.

        Returns the number of messages processed this cycle.
        """
        messages = await self._bus.reclaim(
            stream=self._stream,
            group=self._group,
            consumer=self._consumer,
            min_idle_ms=self._reclaim_idle_ms,
            count=self._batch,
        )
        if not messages:
            messages = await self._bus.read(
                stream=self._stream,
                group=self._group,
                consumer=self._consumer,
                count=self._batch,
                block_ms=self._block_ms,
            )
        for message in messages:
            await self._process(message)
        return len(messages)

    async def _process(self, message: StreamMessage) -> None:
        if self._dedupe is not None:
            event_id = str(message.payload.get(self._id_field, ""))
            if event_id and not await self._dedupe(event_id):
                await self._ack(message)  # already processed; drop duplicate
                return
        try:
            await self._handler(message.payload)
        except Exception:
            self._attempts[message.id] += 1
            attempts = self._attempts[message.id]
            logger.warning(
                "stream_consumer.handler_failed",
                stream=self._stream,
                message_id=message.id,
                attempt=attempts,
            )
            if attempts >= self._max_attempts:
                await self._bus.dead_letter(
                    self._stream, message.payload, reason="max_attempts_exceeded"
                )
                await self._ack(message)
            return
        await self._ack(message)

    async def _ack(self, message: StreamMessage) -> None:
        await self._bus.ack(stream=self._stream, group=self._group, message_id=message.id)
        self._attempts.pop(message.id, None)

    async def run(self, stop: asyncio.Event) -> None:
        await self._bus.ensure_group(self._stream, self._group)
        logger.info("stream_consumer.started", stream=self._stream, group=self._group)
        while not stop.is_set():
            try:
                processed = await self.poll_once()
            except Exception:
                logger.warning("stream_consumer.poll_failed", stream=self._stream)
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=2)
                continue
            if processed == 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=0.1)
