"""Typed facade over redis.asyncio.

Keeps redis-py's loosely typed API out of application code and centralizes
serialization. Redis holds only disposable coordination/cache state.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable
from typing import Any, cast

import redis.asyncio as aioredis


def _decode_stream_entries(entries: Any) -> list[tuple[str, dict[str, Any]]]:
    """Decode ``[(id, {"payload": json})]`` stream entries to ``[(id, payload)]``.

    Malformed entries are surfaced with an empty payload so the consumer can ack
    and dead-letter them rather than looping forever on a poison message.
    """
    decoded: list[tuple[str, dict[str, Any]]] = []
    for entry_id, fields in entries:
        raw = fields.get("payload") if isinstance(fields, dict) else None
        try:
            payload = cast(dict[str, Any], json.loads(raw)) if raw else {}
        except (json.JSONDecodeError, TypeError):
            payload = {}
        decoded.append((str(entry_id), payload))
    return decoded


class RedisGateway:
    def __init__(self, client: aioredis.Redis) -> None:
        self._client = client

    @classmethod
    def from_url(cls, url: str) -> RedisGateway:
        return cls(aioredis.Redis.from_url(url, decode_responses=True))

    @property
    def raw(self) -> aioredis.Redis:
        return self._client

    async def ping(self) -> bool:
        try:
            await self._client.ping()
        except Exception:
            return False
        return True

    async def close(self) -> None:
        await self._client.aclose()

    async def get_str(self, key: str) -> str | None:
        value = await cast(Awaitable[str | None], self._client.get(key))
        return value

    async def set_str(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        await cast(Awaitable[Any], self._client.set(key, value, ex=ttl_seconds))

    async def delete(self, *keys: str) -> None:
        if keys:
            await cast(Awaitable[Any], self._client.delete(*keys))

    async def get_json(self, key: str) -> dict[str, Any] | None:
        raw = await self.get_str(key)
        if raw is None:
            return None
        loaded = json.loads(raw)
        return cast(dict[str, Any], loaded)

    async def set_json(
        self, key: str, value: dict[str, Any], *, ttl_seconds: int | None = None
    ) -> None:
        await self.set_str(key, json.dumps(value, default=str), ttl_seconds=ttl_seconds)

    async def incr_fixed_window(self, key: str, window_seconds: int) -> int:
        """Fixed-window counter used for rate limiting."""
        pipe = self._client.pipeline()
        pipe.incr(key)
        pipe.expire(key, window_seconds, nx=True)
        results = await pipe.execute()
        return int(results[0])

    async def sliding_window_hit(
        self, key: str, *, window_ms: int, now_ms: int, member: str
    ) -> int:
        """Record a hit and return the number of hits within the sliding window.

        Implemented as a sorted-set log: expired entries are trimmed, this hit is
        added scored by timestamp, and the current cardinality is returned. One
        pipeline round-trip per call.
        """
        cutoff = now_ms - window_ms
        pipe = self._client.pipeline()
        pipe.zremrangebyscore(key, 0, cutoff)
        pipe.zadd(key, {member: now_ms})
        pipe.zcard(key)
        pipe.pexpire(key, window_ms)
        results = await pipe.execute()
        return int(results[2])

    async def hset_json(self, key: str, field: str, value: dict[str, Any]) -> None:
        await cast(Awaitable[Any], self._client.hset(key, field, json.dumps(value, default=str)))

    async def hget_json(self, key: str, field: str) -> dict[str, Any] | None:
        raw = await cast(Awaitable[str | None], self._client.hget(key, field))
        if raw is None:
            return None
        return cast(dict[str, Any], json.loads(raw))

    async def hgetall_json(self, key: str) -> dict[str, dict[str, Any]]:
        raw = await cast(Awaitable[dict[str, str]], self._client.hgetall(key))
        return {field: cast(dict[str, Any], json.loads(value)) for field, value in raw.items()}

    async def hincrby(self, key: str, field: str, amount: int = 1) -> int:
        return int(await self._client.hincrby(key, field, amount))

    async def hgetall_int(self, key: str) -> dict[str, int]:
        raw = await cast(Awaitable[dict[str, str]], self._client.hgetall(key))
        return {field: int(value) for field, value in raw.items()}

    async def expire(self, key: str, ttl_seconds: int) -> None:
        await cast(Awaitable[Any], self._client.expire(key, ttl_seconds))

    async def publish_json(self, channel: str, payload: dict[str, Any]) -> None:
        await cast(Awaitable[Any], self._client.publish(channel, json.dumps(payload, default=str)))

    async def xadd_json(
        self, stream: str, payload: dict[str, Any], *, maxlen: int = 100_000
    ) -> None:
        await cast(
            Awaitable[Any],
            self._client.xadd(
                stream,
                {"payload": json.dumps(payload, default=str)},
                maxlen=maxlen,
                approximate=True,
            ),
        )

    async def xadd_event(
        self, stream: str, payload: dict[str, Any], *, maxlen: int = 100_000
    ) -> str:
        """Append a payload-wrapped event and return its stream id."""
        message_id = await cast(
            Awaitable[Any],
            self._client.xadd(
                stream,
                {"payload": json.dumps(payload, default=str)},
                maxlen=maxlen,
                approximate=True,
            ),
        )
        return str(message_id)

    async def xgroup_ensure(self, stream: str, group: str) -> None:
        try:
            await cast(
                Awaitable[Any],
                self._client.xgroup_create(stream, group, id="0-0", mkstream=True),
            )
        except Exception as error:
            if "BUSYGROUP" not in str(error):
                raise

    async def xreadgroup_events(
        self, *, stream: str, group: str, consumer: str, count: int, block_ms: int
    ) -> list[tuple[str, dict[str, Any]]]:
        response = await cast(
            Awaitable[Any],
            self._client.xreadgroup(
                group, consumer, {stream: ">"}, count=count, block=block_ms
            ),
        )
        if not response:
            return []
        return _decode_stream_entries(response[0][1])

    async def xautoclaim_events(
        self, *, stream: str, group: str, consumer: str, min_idle_ms: int, count: int
    ) -> list[tuple[str, dict[str, Any]]]:
        claimed = await cast(
            Awaitable[Any],
            self._client.xautoclaim(
                stream, group, consumer, min_idle_time=min_idle_ms, start_id="0-0", count=count
            ),
        )
        entries = claimed[1] if claimed and len(claimed) > 1 else []
        return _decode_stream_entries(entries)

    async def xack(self, stream: str, group: str, message_id: str) -> None:
        await cast(Awaitable[Any], self._client.xack(stream, group, message_id))

    async def xlen(self, stream: str) -> int:
        """Number of entries currently retained in a stream (0 if absent)."""
        try:
            return int(await cast(Awaitable[Any], self._client.xlen(stream)))
        except Exception:
            return 0

    async def consumer_group_lag(self, stream: str, group: str) -> int:
        """Undelivered + unacked backlog for a consumer group.

        Uses the ``lag`` reported by ``XINFO GROUPS`` (Redis 7+) when available,
        falling back to the pending count. Returns 0 when the stream/group does
        not exist yet so a cold system reports no backlog rather than erroring.
        """
        try:
            groups = await cast(Awaitable[Any], self._client.xinfo_groups(stream))
        except Exception:
            return 0
        for info in groups:
            name = info.get("name")
            if isinstance(name, bytes):
                name = name.decode()
            if name != group:
                continue
            lag = info.get("lag")
            if lag is not None:
                return max(0, int(lag))
            return max(0, int(info.get("pending", 0)))
        return 0

    async def set_if_absent(self, key: str, *, ttl_seconds: int) -> bool:
        """Atomically set ``key`` only if absent; True when newly set (SET NX EX)."""
        result = await cast(
            Awaitable[Any], self._client.set(key, "1", nx=True, ex=ttl_seconds)
        )
        return bool(result)

    async def subscribe_json(self, *channels: str) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """Yield (channel, payload) tuples for pattern-free channel subscriptions."""
        pubsub = self._client.pubsub()
        await pubsub.subscribe(*channels)
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                channel = str(message.get("channel"))
                try:
                    payload = cast(dict[str, Any], json.loads(str(message.get("data"))))
                except json.JSONDecodeError:
                    continue
                yield channel, payload
        finally:
            await pubsub.unsubscribe()
            await pubsub.aclose()  # type: ignore[no-untyped-call]
