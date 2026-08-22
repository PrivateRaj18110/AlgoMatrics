from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column

from algo_platform.shared.infrastructure.database import Base


class WorkspaceTaskModel(Base):
    __tablename__ = "workspace_tasks"
    __table_args__ = (Index("ix_workspace_tasks_org_user", "organization_id", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID]
    user_id: Mapped[uuid.UUID]
    title: Mapped[str] = mapped_column(String(300))
    notes: Mapped[str | None] = mapped_column(String(2000), default=None)
    priority: Mapped[str] = mapped_column(String(10), default="normal")
    due_at: Mapped[datetime | None] = mapped_column(default=None)
    completed_at: Mapped[datetime | None] = mapped_column(default=None)
    archived_at: Mapped[datetime | None] = mapped_column(default=None)
    tag: Mapped[str | None] = mapped_column(String(60), default=None)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
