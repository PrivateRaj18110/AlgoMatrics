"""Log line ORM model — structured log feed, filterable by source."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class Log(Base):
    __tablename__ = "logs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    envelope_id: Mapped[str | None] = mapped_column(String, nullable=True)

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    level: Mapped[str] = mapped_column(String, nullable=False)
    logger: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Soft reference to machines.id (indexed; no hard FK — see Event model).
    machine_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("uq_logs_envelope_id", "envelope_id", unique=True),
        # The hot path is `by_source(...)` newest-first; a composite on
        # (source, time) serves both the filter and the ordering.
        Index("ix_logs_source_time", "source", "time"),
        Index("ix_logs_time", "time"),
        Index("ix_logs_machine_id", "machine_id"),
    )
