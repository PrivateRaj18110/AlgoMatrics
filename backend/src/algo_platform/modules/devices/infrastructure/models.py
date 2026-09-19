from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from algo_platform.shared.infrastructure.database import Base


class DeviceModel(Base):
    """A trading machine allowed to report to one organization."""

    __tablename__ = "devices"
    __table_args__ = (Index("ix_devices_org", "organization_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID]
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(40), default="trading")
    key_prefix: Mapped[str] = mapped_column(String(16))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
    created_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None] = mapped_column(default=None)
    last_seen_at: Mapped[datetime | None] = mapped_column(default=None)
    last_ip: Mapped[str | None] = mapped_column(String(45), default=None)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(default=None)
    health: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    positions: Mapped[list[Any] | None] = mapped_column(JSONB, default=None)
    positions_at: Mapped[datetime | None] = mapped_column(default=None)


class DeviceEventModel(Base):
    """A trade, log line or alert a device reported. Heartbeats are not stored here."""

    __tablename__ = "device_events"
    __table_args__ = (
        Index("ix_device_events_device_time", "device_id", "occurred_at"),
        Index("ix_device_events_org_time", "organization_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"))
    organization_id: Mapped[uuid.UUID]
    kind: Mapped[str] = mapped_column(String(20))
    severity: Mapped[str] = mapped_column(String(10))
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    occurred_at: Mapped[datetime]
    received_at: Mapped[datetime]
