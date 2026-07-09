from __future__ import annotations

import uuid
from datetime import datetime, time
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Time, UniqueConstraint
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


class NotificationPreferenceModel(Base):
    """A recipient's multi-channel delivery policy (one row per user/org)."""

    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_notification_prefs_org_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID]
    user_id: Mapped[uuid.UUID]
    # JSON string lists so the policy stays flexible without a migration per tweak.
    enabled_channels: Mapped[list[str]] = mapped_column(default=lambda: ["in_app"])
    muted_types: Mapped[list[str]] = mapped_column(default=list)
    min_severity: Mapped[str] = mapped_column(String(10), default="info")
    quiet_start: Mapped[time | None] = mapped_column(Time(), default=None)
    quiet_end: Mapped[time | None] = mapped_column(Time(), default=None)
    critical_overrides_quiet: Mapped[bool] = mapped_column(Boolean(), default=True)
    webhook_url: Mapped[str | None] = mapped_column(String(500), default=None)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
