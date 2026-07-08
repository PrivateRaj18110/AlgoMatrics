"""Lightweight operational counters kept in Redis day buckets.

These power the admin business-metrics endpoint and request performance
tracking. They intentionally avoid high-cardinality labels; deep observability
belongs to the OpenTelemetry pipeline.
"""

from __future__ import annotations

from datetime import UTC, datetime

from algo_platform.shared.infrastructure.redis_gateway import RedisGateway

_RETENTION_SECONDS = 60 * 60 * 24 * 45


def _day_key(day: datetime | None = None) -> str:
    moment = day or datetime.now(UTC)
    return f"metrics:{moment:%Y%m%d}"


class MetricsRecorder:
    def __init__(self, redis: RedisGateway) -> None:
        self._redis = redis

    async def incr(self, name: str, amount: int = 1) -> None:
        key = _day_key()
        await self._redis.hincrby(key, name, amount)
        await self._redis.expire(key, _RETENTION_SECONDS)

    async def observe_ms(self, name: str, elapsed_ms: int) -> None:
        key = _day_key()
        await self._redis.hincrby(key, f"{name}:sum_ms", elapsed_ms)
        await self._redis.hincrby(key, f"{name}:count", 1)
        await self._redis.expire(key, _RETENTION_SECONDS)

    async def snapshot(self, day: datetime | None = None) -> dict[str, int]:
        return await self._redis.hgetall_int(_day_key(day))
