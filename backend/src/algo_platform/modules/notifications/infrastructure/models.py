from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from algo_platform.shared.infrastructure.database import Base


class NotificationModel(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_org_user_time", "organization_id", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID]
    # NULL user_id = broadcast to every member of the organization.
    user_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    type: Mapped[str] = mapped_column(String(60))
    severity: Mapped[str] = mapped_column(String(10), default="info")
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(String(2000), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    read_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class NotificationReadModel(Base):
    """Per-user read receipt for organization-wide notifications."""

    __tablename__ = "notification_reads"
    __table_args__ = (
        UniqueConstraint("notification_id", "user_id"),
        Index("ix_notification_reads_user", "user_id", "read_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    notification_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notifications.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID]
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
