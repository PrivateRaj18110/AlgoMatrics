from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, TypeVar

from algo_platform.shared.domain.types import DomainEvent

T = TypeVar("T")
EventHandler = Callable[[DomainEvent], Awaitable[None]]


class UnitOfWork(Protocol):
    async def __aenter__(self) -> UnitOfWork: ...

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


class EventPublisher(Protocol):
    async def publish(self, event: DomainEvent) -> None: ...


class DistributedLock(Protocol):
    async def acquire(self, key: str, ttl_seconds: int) -> bool: ...

    async def release(self, key: str) -> None: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


@dataclass(frozen=True, slots=True)
class EmailMessage:
    to: str
    subject: str
    text: str
    html: str | None = None


class EmailSender(Protocol):
    async def send(self, message: EmailMessage) -> None: ...
