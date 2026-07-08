"""Redis Streams implementation of the :class:`EventBus` port."""

from __future__ import annotations

from typing import Any

from algo_platform.shared.application.event_bus import StreamMessage
from algo_platform.shared.infrastructure.redis_gateway import RedisGateway


class RedisStreamsEventBus:
    def __init__(self, redis: RedisGateway) -> None:
        self._redis = redis

    async def publish(self, stream: str, payload: dict[str, Any]) -> str:
        return await self._redis.xadd_event(stream, payload)

    async def ensure_group(self, stream: str, group: str) -> None:
        await self._redis.xgroup_ensure(stream, group)

    async def read(
        self, *, stream: str, group: str, consumer: str, count: int, block_ms: int
    ) -> list[StreamMessage]:
        entries = await self._redis.xreadgroup_events(
            stream=stream, group=group, consumer=consumer, count=count, block_ms=block_ms
        )
        return [StreamMessage(id=mid, payload=payload) for mid, payload in entries]

    async def reclaim(
        self, *, stream: str, group: str, consumer: str, min_idle_ms: int, count: int
    ) -> list[StreamMessage]:
        entries = await self._redis.xautoclaim_events(
            stream=stream, group=group, consumer=consumer, min_idle_ms=min_idle_ms, count=count
        )
        return [StreamMessage(id=mid, payload=payload) for mid, payload in entries]

    async def ack(self, *, stream: str, group: str, message_id: str) -> None:
        await self._redis.xack(stream, group, message_id)

    async def dead_letter(self, stream: str, payload: dict[str, Any], *, reason: str) -> str:
        return await self._redis.xadd_event(
            f"{stream}:dlq", {"reason": reason, "event": payload}
        )
