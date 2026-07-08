"""Inbox idempotency: turn at-least-once delivery into effectively-once.

Records processed event ids so a redelivered message (crash between handling and
ack, or a reclaim) is not applied twice. Backed by a Redis SET NX with a
retention TTL long enough to cover realistic redelivery windows.
"""

from __future__ import annotations

from algo_platform.shared.infrastructure.redis_gateway import RedisGateway

# One week comfortably exceeds any reclaim/redelivery window.
_DEFAULT_TTL_SECONDS = 7 * 24 * 60 * 60


class RedisInbox:
    def __init__(self, redis: RedisGateway, *, ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
        self._redis = redis
        self._ttl = ttl_seconds

    async def claim(self, event_id: str) -> bool:
        """Return True if this event id is new (proceed); False if already seen."""
        return await self._redis.set_if_absent(f"inbox:{event_id}", ttl_seconds=self._ttl)
