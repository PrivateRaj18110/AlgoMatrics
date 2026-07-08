"""Unit tests for the domain event-consumer workers (Phase 7, slice B)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from algo_platform.processes.workers.consumer_worker import EventConsumerWorker
from algo_platform.processes.workers.handlers import analytics_handler
from algo_platform.processes.workers.registry import REGISTRY, available_roles


def _worker(handler: Any, prefixes: tuple[str, ...] | None) -> EventConsumerWorker:
    ctx = SimpleNamespace(metrics=None)
    return EventConsumerWorker(
        ctx,  # type: ignore[arg-type]
        name="test",
        group="worker:test",
        handler=handler,
        event_prefixes=prefixes,
    )


async def test_prefix_filter_skips_non_matching_events() -> None:
    seen: list[str] = []

    async def handler(ctx: Any, event: dict[str, Any]) -> None:
        seen.append(str(event["event_type"]))

    worker = _worker(handler, ("trading.",))
    await worker._on_event({"event_type": "billing.payment_succeeded.v1"})
    await worker._on_event({"event_type": "trading.order_placed.v1"})
    assert seen == ["trading.order_placed.v1"]


async def test_none_prefix_matches_all_events() -> None:
    seen: list[str] = []

    async def handler(ctx: Any, event: dict[str, Any]) -> None:
        seen.append(str(event["event_type"]))

    worker = _worker(handler, None)
    await worker._on_event({"event_type": "anything.happened.v1"})
    assert seen == ["anything.happened.v1"]


class _FakeRedis:
    def __init__(self) -> None:
        self.hashes: dict[str, dict[str, int]] = {}
        self.expired: list[str] = []

    async def hincrby(self, key: str, field: str, amount: int = 1) -> int:
        bucket = self.hashes.setdefault(key, {})
        bucket[field] = bucket.get(field, 0) + amount
        return bucket[field]

    async def expire(self, key: str, ttl_seconds: int) -> None:
        self.expired.append(key)


async def test_analytics_handler_counts_events_per_type() -> None:
    redis = _FakeRedis()
    ctx = SimpleNamespace(redis=redis)
    await analytics_handler(ctx, {"event_type": "trading.order_placed.v1"})  # type: ignore[arg-type]
    await analytics_handler(ctx, {"event_type": "trading.order_placed.v1"})  # type: ignore[arg-type]
    await analytics_handler(ctx, {"event_type": "billing.payment_succeeded.v1"})  # type: ignore[arg-type]

    (key,) = redis.hashes  # single day bucket
    assert redis.hashes[key]["trading.order_placed.v1"] == 2
    assert redis.hashes[key]["billing.payment_succeeded.v1"] == 1
    assert redis.expired  # TTL applied


def test_registry_contains_all_eight_worker_roles() -> None:
    assert set(available_roles()) == {
        "relay",
        "email",
        "notification",
        "analytics",
        "audit",
        "report",
        "billing",
        "settlement",
        "trading",
    }
    for name in available_roles():
        assert name in REGISTRY
