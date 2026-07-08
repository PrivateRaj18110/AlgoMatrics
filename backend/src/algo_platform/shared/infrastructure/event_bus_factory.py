"""Construct the configured :class:`EventBus` backend."""

from __future__ import annotations

from algo_platform.config import Settings
from algo_platform.shared.application.event_bus import EventBus
from algo_platform.shared.infrastructure.event_bus_redis import RedisStreamsEventBus
from algo_platform.shared.infrastructure.redis_gateway import RedisGateway


def build_event_bus(settings: Settings, redis: RedisGateway) -> EventBus:
    backend = settings.event_bus_backend
    if backend == "redis":
        return RedisStreamsEventBus(redis)
    # Kafka/NATS/RabbitMQ implement the same EventBus port; they are recognised
    # by configuration but not yet wired in this build.
    raise NotImplementedError(f"event bus backend '{backend}' is not available in this build")
