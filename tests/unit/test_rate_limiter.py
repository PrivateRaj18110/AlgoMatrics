"""Unit tests for the sliding-window rate limiter (Phase 5, slice A)."""

from __future__ import annotations

import pytest

from algo_platform.shared.infrastructure.rate_limiting.limiter import (
    RateLimiter,
    RateLimitRule,
)


class InMemoryWindowStore:
    """Exact sliding-window log kept in memory for deterministic tests."""

    def __init__(self) -> None:
        self._hits: dict[str, list[int]] = {}

    async def hit(self, key: str, *, window_ms: int, now_ms: int) -> int:
        bucket = self._hits.setdefault(key, [])
        cutoff = now_ms - window_ms
        bucket[:] = [t for t in bucket if t > cutoff]
        bucket.append(now_ms)
        return len(bucket)


def test_rule_rejects_invalid_config() -> None:
    with pytest.raises(ValueError):
        RateLimitRule(limit=0, window_seconds=60)
    with pytest.raises(ValueError):
        RateLimitRule(limit=10, window_seconds=0)


async def test_allows_up_to_limit_then_blocks() -> None:
    limiter = RateLimiter(InMemoryWindowStore())
    rule = RateLimitRule(limit=3, window_seconds=60)
    now = 1_000_000
    results = [await limiter.check("user:1", rule, now_ms=now + i) for i in range(4)]
    assert [r.allowed for r in results] == [True, True, True, False]
    assert results[2].remaining == 0
    assert results[3].retry_after_seconds == 60


async def test_window_slides_and_frees_capacity() -> None:
    limiter = RateLimiter(InMemoryWindowStore())
    rule = RateLimitRule(limit=2, window_seconds=1)
    assert (await limiter.check("ip:x", rule, now_ms=0)).allowed
    assert (await limiter.check("ip:x", rule, now_ms=100)).allowed
    assert not (await limiter.check("ip:x", rule, now_ms=200)).allowed
    # After the window fully passes, capacity is restored.
    assert (await limiter.check("ip:x", rule, now_ms=1_500)).allowed


async def test_keys_are_isolated() -> None:
    limiter = RateLimiter(InMemoryWindowStore())
    rule = RateLimitRule(limit=1, window_seconds=60)
    assert (await limiter.check("tenant:a", rule, now_ms=0)).allowed
    # Different key has its own budget.
    assert (await limiter.check("tenant:b", rule, now_ms=0)).allowed
    assert not (await limiter.check("tenant:a", rule, now_ms=1)).allowed


async def test_burst_limit_blocks_spikes_within_sustained_headroom() -> None:
    limiter = RateLimiter(InMemoryWindowStore())
    # Sustained 100/min but only 2 per second.
    rule = RateLimitRule(limit=100, window_seconds=60, burst_limit=2, burst_window_seconds=1)
    assert (await limiter.check("route:x", rule, now_ms=0)).allowed
    assert (await limiter.check("route:x", rule, now_ms=100)).allowed
    blocked = await limiter.check("route:x", rule, now_ms=200)
    assert not blocked.allowed
    assert blocked.retry_after_seconds == 1
    # Next second the burst window resets while sustained still has room.
    assert (await limiter.check("route:x", rule, now_ms=1_100)).allowed


async def test_remaining_counts_down() -> None:
    limiter = RateLimiter(InMemoryWindowStore())
    rule = RateLimitRule(limit=5, window_seconds=60)
    first = await limiter.check("k", rule, now_ms=0)
    assert first.remaining == 4
    second = await limiter.check("k", rule, now_ms=1)
    assert second.remaining == 3
