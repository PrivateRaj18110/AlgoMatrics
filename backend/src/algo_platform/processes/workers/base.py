"""Worker-role contract and the shared context handed to every role."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from algo_platform.config import Settings
from algo_platform.shared.application.event_bus import EventBus
from algo_platform.shared.application.ports import EmailSender
from algo_platform.shared.infrastructure.prometheus import PrometheusMetrics
from algo_platform.shared.infrastructure.redis_gateway import RedisGateway


@dataclass(slots=True)
class WorkerContext:
    """Shared per-process resources passed to each worker role."""

    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]
    redis: RedisGateway
    event_bus: EventBus
    email_sender: EmailSender
    metrics: PrometheusMetrics | None


class WorkerRole(Protocol):
    """A single, independently schedulable unit of background work."""

    name: str

    async def run(self, stop: asyncio.Event) -> None:
        """Run until ``stop`` is set. Must return promptly once it is."""
        ...
