"""Transactional outbox: durable event records written with aggregate changes."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Index, String, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from algo_platform.shared.domain.types import DomainEvent, utc_now
from algo_platform.shared.infrastructure.database import Base


class OutboxEventModel(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index(
            "ix_outbox_events_unpublished",
            "occurred_at",
            postgresql_where=text("published_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(unique=True)
    event_type: Mapped[str] = mapped_column(String(120))
    schema_version: Mapped[int] = mapped_column(default=1)
    aggregate_type: Mapped[str] = mapped_column(String(60))
    aggregate_id: Mapped[uuid.UUID]
    organization_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    headers: Mapped[dict[str, Any]] = mapped_column(default=dict)
    published_at: Mapped[datetime | None] = mapped_column(default=None)
    attempts: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


async def enqueue_event(
    session: AsyncSession,
    *,
    event: DomainEvent,
    aggregate_type: str,
    payload: dict[str, Any],
    correlation_id: str | None = None,
) -> None:
    session.add(
        OutboxEventModel(
            event_id=event.event_id,
            event_type=event.event_type,
            schema_version=event.schema_version,
            aggregate_type=aggregate_type,
            aggregate_id=event.aggregate_id,
            organization_id=event.tenant_id,
            occurred_at=event.occurred_at,
            payload=payload,
            headers={"correlation_id": correlation_id} if correlation_id else {},
        )
    )


async def enqueue_engine_command(
    session: AsyncSession,
    *,
    command_type: str,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    organization_id: uuid.UUID,
    payload: dict[str, Any],
) -> uuid.UUID:
    """Persist an engine command in the caller's transaction."""
    command_id = uuid.uuid4()
    session.add(
        OutboxEventModel(
            event_id=command_id,
            event_type="engine.command.v1",
            schema_version=1,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            organization_id=organization_id,
            occurred_at=utc_now(),
            payload={"type": command_type, **payload},
            headers={},
        )
    )
    return command_id


async def fetch_unpublished(session: AsyncSession, *, limit: int = 200) -> list[OutboxEventModel]:
    result = await session.execute(
        select(OutboxEventModel)
        .where(OutboxEventModel.published_at.is_(None))
        .order_by(OutboxEventModel.occurred_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list(result.scalars().all())


async def mark_published(session: AsyncSession, event_ids: list[uuid.UUID]) -> None:
    if not event_ids:
        return
    await session.execute(
        update(OutboxEventModel)
        .where(OutboxEventModel.event_id.in_(event_ids))
        .values(published_at=utc_now(), attempts=OutboxEventModel.attempts + 1)
    )
