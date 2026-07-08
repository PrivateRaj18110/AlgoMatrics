"""Redis sorted-set implementation of :class:`WindowStore`."""

from __future__ import annotations

import secrets

from algo_platform.shared.infrastructure.redis_gateway import RedisGateway


class RedisWindowStore:
    def __init__(self, redis: RedisGateway) -> None:
        self._redis = redis

    async def hit(self, key: str, *, window_ms: int, now_ms: int) -> int:
        # A unique member per hit keeps entries distinct even within the same
        # millisecond, so the sorted-set count is exact.
        member = f"{now_ms}-{secrets.token_hex(6)}"
        return await self._redis.sliding_window_hit(
            key, window_ms=window_ms, now_ms=now_ms, member=member
        )
