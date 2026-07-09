from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from algo_platform.shared.infrastructure.database import Base


class MobileDeviceModel(Base):
    """A registered mobile device holding a push token for one user."""

    __tablename__ = "mobile_devices"
    __table_args__ = (
        # A push token is globally unique to a device install; re-registering
        # updates the owning user rather than creating a duplicate row.
        UniqueConstraint("push_token", name="uq_mobile_devices_push_token"),
        Index("ix_mobile_devices_org_user", "organization_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID]
    user_id: Mapped[uuid.UUID]
    platform: Mapped[str] = mapped_column(String(10))
    push_token: Mapped[str] = mapped_column(String(4096))
    app_version: Mapped[str | None] = mapped_column(String(40), default=None)
    device_name: Mapped[str | None] = mapped_column(String(120), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
