"""Unit tests for the reusable stream consumer runner (Phase 6, slice B)."""

from __future__ import annotations

from typing import Any

from algo_platform.shared.application.event_bus import StreamMessage
from algo_platform.shared.infrastructure.stream_consumer import StreamConsumer


class FakeBus:
    """In-memory EventBus: scripted reads, records acks and dead-letters."""

    def __init__(self) -> None:
        self.groups: list[tuple[str, str]] = []
        self.read_batches: list[list[StreamMessage]] = []
        self.reclaim_batches: list[list[StreamMessage]] = []
        self.acked: list[str] = []
        self.dead: list[tuple[str, dict[str, Any], str]] = []

    async def publish(self, stream: str, payload: dict[str, Any]) -> str:
        return "1-0"

    async def ensure_group(self, stream: str, group: str) -> None:
        self.groups.append((stream, group))

    async def read(self, *, stream: str, group: str, consumer: str, count: int, block_ms: int):
        return self.read_batches.pop(0) if self.read_batches else []

    async def reclaim(
        self, *, stream: str, group: str, consumer: str, min_idle_ms: int, count: int
    ):
        return self.reclaim_batches.pop(0) if self.reclaim_batches else []

    async def ack(self, *, stream: str, group: str, message_id: str) -> None:
        self.acked.append(message_id)

    async def dead_letter(self, stream: str, payload: dict[str, Any], *, reason: str) -> str:
        self.dead.append((stream, payload, reason))
        return "dlq-1"


def _consumer(bus: FakeBus, handler, **kw: Any) -> StreamConsumer:
    return StreamConsumer(
        bus, stream="events", group="g", consumer="c1", handler=handler, **kw  # type: ignore[arg-type]
    )


async def test_successful_message_is_acked() -> None:
    bus = FakeBus()
    bus.read_batches = [[StreamMessage(id="1-0", payload={"event_id": "e1"})]]
    seen: list[dict[str, Any]] = []

    async def handler(payload: dict[str, Any]) -> None:
        seen.append(payload)

    processed = await _consumer(bus, handler).poll_once()
    assert processed == 1
    assert seen == [{"event_id": "e1"}]
    assert bus.acked == ["1-0"]


async def test_failing_message_is_not_acked_until_max_then_dead_lettered() -> None:
    bus = FakeBus()
    msg = StreamMessage(id="1-0", payload={"event_id": "e1"})

    async def handler(payload: dict[str, Any]) -> None:
        raise RuntimeError("boom")

    consumer = _consumer(bus, handler, max_attempts=3)
    # First two attempts: no ack, no DLQ (will be reclaimed and retried).
    bus.read_batches = [[msg]]
    await consumer.poll_once()
    bus.read_batches = [[msg]]
    await consumer.poll_once()
    assert bus.acked == [] and bus.dead == []
    # Third attempt hits max_attempts: dead-lettered and acked.
    bus.read_batches = [[msg]]
    await consumer.poll_once()
    assert bus.dead == [("events", {"event_id": "e1"}, "max_attempts_exceeded")]
    assert bus.acked == ["1-0"]


async def test_reclaim_takes_priority_over_read() -> None:
    bus = FakeBus()
    bus.reclaim_batches = [[StreamMessage(id="9-0", payload={"event_id": "stale"})]]
    bus.read_batches = [[StreamMessage(id="1-0", payload={"event_id": "new"})]]
    handled: list[str] = []

    async def handler(payload: dict[str, Any]) -> None:
        handled.append(str(payload["event_id"]))

    await _consumer(bus, handler).poll_once()
    # Only the reclaimed message is processed this cycle.
    assert handled == ["stale"]
    assert bus.acked == ["9-0"]


async def test_dedupe_skips_already_processed_events() -> None:
    bus = FakeBus()
    bus.read_batches = [[StreamMessage(id="1-0", payload={"event_id": "dup"})]]
    handled: list[str] = []
    seen_ids: set[str] = {"dup"}  # pretend "dup" was already processed

    async def handler(payload: dict[str, Any]) -> None:
        handled.append(str(payload["event_id"]))

    async def dedupe(event_id: str) -> bool:
        return event_id not in seen_ids

    await _consumer(bus, handler, dedupe=dedupe).poll_once()
    assert handled == []  # handler never called for the duplicate
    assert bus.acked == ["1-0"]  # duplicate is acked and dropped
