from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from algo_platform.shared.infrastructure.database import Base


class AuditLogModel(Base):
    """Append-only audit evidence; rows are never updated or deleted."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_org_time", "organization_id", "occurred_at"),
        Index("ix_audit_log_actor_time", "actor_user_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    actor_type: Mapped[str] = mapped_column(String(20), default="user")
    action: Mapped[str] = mapped_column(String(120))
    resource_type: Mapped[str] = mapped_column(String(60))
    resource_id: Mapped[str] = mapped_column(String(64), default="")
    request_id: Mapped[str | None] = mapped_column(String(64), default=None)
    ip_hash: Mapped[str | None] = mapped_column(String(64), default=None)
    before_state: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    after_state: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
