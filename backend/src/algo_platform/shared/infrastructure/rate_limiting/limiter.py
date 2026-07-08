"""Sliding-window rate limiter with optional burst control.

The counting backend is abstracted behind :class:`WindowStore` so the limiter's
decision logic is unit testable in memory; production uses the Redis sorted-set
implementation. Each rule may carry a short burst window in addition to the
sustained window, and both must pass for a request to be allowed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class WindowStore(Protocol):
    async def hit(self, key: str, *, window_ms: int, now_ms: int) -> int:
        """Record one hit at ``now_ms`` and return the count within the window."""
        ...


@dataclass(frozen=True, slots=True)
class RateLimitRule:
    limit: int
    window_seconds: int
    # Optional short-window burst cap; e.g. 20 requests within 1 second even if
    # the sustained per-minute limit has headroom.
    burst_limit: int | None = None
    burst_window_seconds: int = 1

    def __post_init__(self) -> None:
        if self.limit < 1 or self.window_seconds < 1:
            raise ValueError("rate limit and window must be >= 1")


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int


class RateLimiter:
    def __init__(self, store: WindowStore) -> None:
        self._store = store

    async def check(self, key: str, rule: RateLimitRule, *, now_ms: int) -> RateLimitResult:
        sustained = await self._store.hit(
            f"{key}:s", window_ms=rule.window_seconds * 1000, now_ms=now_ms
        )
        if sustained > rule.limit:
            return RateLimitResult(
                allowed=False,
                limit=rule.limit,
                remaining=0,
                retry_after_seconds=rule.window_seconds,
            )

        if rule.burst_limit is not None:
            burst = await self._store.hit(
                f"{key}:b", window_ms=rule.burst_window_seconds * 1000, now_ms=now_ms
            )
            if burst > rule.burst_limit:
                return RateLimitResult(
                    allowed=False,
                    limit=rule.burst_limit,
                    remaining=0,
                    retry_after_seconds=rule.burst_window_seconds,
                )

        return RateLimitResult(
            allowed=True,
            limit=rule.limit,
            remaining=max(0, rule.limit - sustained),
            retry_after_seconds=0,
        )
