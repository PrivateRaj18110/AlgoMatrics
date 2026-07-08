# Event-driven architecture (Phase 6)

The platform's event flow — API → transactional outbox → worker relay →
consumers — now runs behind a **transport-agnostic `EventBus` port**, so the
messaging backend can change without rewriting business logic.

```
API writes DomainEvent to the outbox (same txn as the state change)
        │
   worker relay ──publish()──▶ EventBus ──▶ "events" stream
        │                                        │
        └── engine:commands (unchanged)          ▼
                                   StreamConsumer (reclaim → read → handle → ack)
                                        │ poison → {stream}:dlq
                                        └ inbox dedupe → effectively-once
```

## The abstraction

`shared/application/event_bus.py` defines the ports:

- `EventPublisher.publish(stream, payload) -> id`
- `EventConsumer.ensure_group / read / reclaim / ack`
- `EventBus.dead_letter(stream, payload, reason)`

Semantics are consumer-group style: **at-least-once delivery, explicit ack, and
stale-message reclaim**. The Redis Streams implementation
(`RedisStreamsEventBus`) is selected by `EVENT_BUS_BACKEND=redis`. Kafka, NATS,
and RabbitMQ are recognised by configuration and implement the same port when
wired — no business code changes, because business code only depends on the port.

## Building a consumer

`StreamConsumer` encapsulates the delivery loop so a new consumer is just a
handler:

```python
from algo_platform.shared.infrastructure.event_bus_factory import build_event_bus
from algo_platform.shared.infrastructure.inbox import RedisInbox
from algo_platform.shared.infrastructure.stream_consumer import StreamConsumer

bus = build_event_bus(settings, redis)
inbox = RedisInbox(redis)

async def handle(payload: dict[str, object]) -> None:
    ...  # your business logic

consumer = StreamConsumer(
    bus, stream="events", group="notifications", consumer=hostname_pid,
    handler=handle, dedupe=inbox.claim,   # effectively-once
)
await consumer.run(stop_event)
```

- **Retries & DLQ**: a handler that raises is retried (via reclaim); after
  `max_attempts` the message is routed to `events:dlq` and acked so it cannot
  block the group.
- **Idempotency**: pass `dedupe=RedisInbox(...).claim` to skip events already
  processed (guards against redelivery after a crash between handle and ack).

This runner is the building block for the per-domain workers in Phase 7.

## Migration & rollback

- No business-logic rewrite: the worker now calls `EventBus.publish` for the
  events stream with the **same payload-wrapped serialization** as before; the
  `engine:commands` path is unchanged.
- Rollback: set `EVENT_BUS_BACKEND=redis` (the default) — the only implemented
  backend. The change is isolated to the `phase-6-event-driven` branch with no
  schema or API-contract change, so `git revert` is safe.
