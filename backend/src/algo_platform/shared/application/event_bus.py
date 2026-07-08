"""Transport-agnostic event bus port.

Business code publishes and consumes domain events through this interface so the
underlying transport (Redis Streams today; Kafka/NATS/RabbitMQ tomorrow) can be
swapped without touching business logic. Semantics are consumer-group style:
at-least-once delivery, explicit acknowledgement, and stale-message recovery.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class StreamMessage:
    id: str
    payload: dict[str, Any]


class EventPublisher(Protocol):
    async def publish(self, stream: str, payload: dict[str, Any]) -> str:
        """Append an event to ``stream`` and return its transport message id."""
        ...


class EventConsumer(Protocol):
    async def ensure_group(self, stream: str, group: str) -> None:
        """Create the consumer group if it does not exist (idempotent)."""
        ...

    async def read(
        self, *, stream: str, group: str, consumer: str, count: int, block_ms: int
    ) -> list[StreamMessage]:
        """Fetch up to ``count`` new messages for this consumer."""
        ...

    async def reclaim(
        self, *, stream: str, group: str, consumer: str, min_idle_ms: int, count: int
    ) -> list[StreamMessage]:
        """Claim messages pending on a crashed/slow consumer beyond ``min_idle_ms``."""
        ...

    async def ack(self, *, stream: str, group: str, message_id: str) -> None:
        """Acknowledge successful processing so the message is not redelivered."""
        ...


class EventBus(EventPublisher, EventConsumer, Protocol):
    """Publisher + consumer facade for a single transport."""

    async def dead_letter(self, stream: str, payload: dict[str, Any], *, reason: str) -> str:
        """Route a poison/exhausted message to ``{stream}:dlq`` for later inspection."""
        ...
