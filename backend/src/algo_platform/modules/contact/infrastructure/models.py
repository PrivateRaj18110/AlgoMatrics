from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from algo_platform.shared.infrastructure.database import Base


class ContactMessageModel(Base):
    """A message sent through the public "Contact us" form."""

    __tablename__ = "contact_messages"
    __table_args__ = (Index("ix_contact_messages_status_created", "status", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320))
    topic: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")
    ip_address: Mapped[str | None] = mapped_column(String(45), default=None)
    user_agent: Mapped[str | None] = mapped_column(String(400), default=None)
    geo: Mapped[dict[str, Any] | None] = mapped_column(default=None)
    created_at: Mapped[datetime]
    resolved_at: Mapped[datetime | None] = mapped_column(default=None)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(default=None)
