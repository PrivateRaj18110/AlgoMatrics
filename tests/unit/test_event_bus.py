"""Unit tests for the event-bus abstraction (Phase 6, slice A)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from algo_platform.shared.application.event_bus import StreamMessage
from algo_platform.shared.infrastructure.event_bus_redis import RedisStreamsEventBus
from algo_platform.shared.infrastructure.redis_gateway import _decode_stream_entries


def test_decode_stream_entries_parses_payload() -> None:
    entries = [("1-0", {"payload": json.dumps({"event_type": "order.placed", "id": 7})})]
    assert _decode_stream_entries(entries) == [("1-0", {"event_type": "order.placed", "id": 7})]


def test_decode_stream_entries_tolerates_poison() -> None:
    entries = [("1-0", {"payload": "not-json"}), ("2-0", {}), ("3-0", {"payload": None})]
    decoded = _decode_stream_entries(entries)
    # Poison/empty entries decode to an empty payload so they can be acked + DLQ'd.
    assert decoded == [("1-0", {}), ("2-0", {}), ("3-0", {})]


class _FakeGateway:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []
        self.groups: list[tuple[str, str]] = []
        self.acked: list[tuple[str, str, str]] = []
        self._to_read: list[tuple[str, dict[str, Any]]] = []
        self._to_reclaim: list[tuple[str, dict[str, Any]]] = []

    async def xadd_event(
        self, stream: str, payload: dict[str, Any], *, maxlen: int = 100_000
    ) -> str:
        self.published.append((stream, payload))
        return f"{len(self.published)}-0"

    async def xgroup_ensure(self, stream: str, group: str) -> None:
        self.groups.append((stream, group))

    async def xreadgroup_events(
        self, *, stream: str, group: str, consumer: str, count: int, block_ms: int
    ) -> list[tuple[str, dict[str, Any]]]:
        out, self._to_read = self._to_read, []
        return out

    async def xautoclaim_events(
        self, *, stream: str, group: str, consumer: str, min_idle_ms: int, count: int
    ) -> list[tuple[str, dict[str, Any]]]:
        out, self._to_reclaim = self._to_reclaim, []
        return out

    async def xack(self, stream: str, group: str, message_id: str) -> None:
        self.acked.append((stream, group, message_id))


async def test_publish_and_dead_letter() -> None:
    gw = _FakeGateway()
    bus = RedisStreamsEventBus(gw)  # type: ignore[arg-type]
    mid = await bus.publish("events", {"event_type": "x"})
    assert mid == "1-0"
    assert gw.published[0] == ("events", {"event_type": "x"})

    await bus.dead_letter("events", {"bad": 1}, reason="boom")
    stream, payload = gw.published[1]
    assert stream == "events:dlq"
    assert payload == {"reason": "boom", "event": {"bad": 1}}


async def test_read_and_reclaim_map_to_messages() -> None:
    gw = _FakeGateway()
    gw._to_read = [("5-0", {"event_type": "a"})]
    gw._to_reclaim = [("2-0", {"event_type": "old"})]
    bus = RedisStreamsEventBus(gw)  # type: ignore[arg-type]

    read = await bus.read(stream="events", group="g", consumer="c", count=10, block_ms=100)
    assert read == [StreamMessage(id="5-0", payload={"event_type": "a"})]

    reclaimed = await bus.reclaim(
        stream="events", group="g", consumer="c", min_idle_ms=30_000, count=10
    )
    assert reclaimed == [StreamMessage(id="2-0", payload={"event_type": "old"})]


async def test_ensure_group_and_ack_delegate() -> None:
    gw = _FakeGateway()
    bus = RedisStreamsEventBus(gw)  # type: ignore[arg-type]
    await bus.ensure_group("events", "g")
    await bus.ack(stream="events", group="g", message_id="5-0")
    assert gw.groups == [("events", "g")]
    assert gw.acked == [("events", "g", "5-0")]


def test_factory_rejects_unbuilt_backend() -> None:
    from algo_platform.shared.infrastructure.event_bus_factory import build_event_bus

    class _S:
        event_bus_backend = "kafka"

    with pytest.raises(NotImplementedError, match="kafka"):
        build_event_bus(_S(), None)  # type: ignore[arg-type]
