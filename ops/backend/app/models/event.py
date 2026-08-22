"""System event ORM model — one line in the live terminal feed."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class Event(Base):
    __tablename__ = "events"

    # Display id kept in the existing "evt-…" shape so API responses are identical.
    id: Mapped[str] = mapped_column(String, primary_key=True)
    # The originating Envelope id — idempotency key (unique, nullable for the
    # legacy ingest path / seeded rows that have no envelope).
    envelope_id: Mapped[str | None] = mapped_column(String, nullable=True)

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)
    severity: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Soft reference to machines.id (no hard FK: telemetry ingest must never
    # fail or block on machine row ordering). Indexed for joins/filtering.
    machine_id: Mapped[str | None] = mapped_column(String, nullable=True)

    # Phase 3 timeline metadata. These are bounded, dashboard-safe fields; raw
    # telemetry payloads stay out of this table and are never dumped to clients.
    event_type: Mapped[str | None] = mapped_column(String, nullable=True)
    strategy: Mapped[str | None] = mapped_column(String, nullable=True)
    symbol: Mapped[str | None] = mapped_column(String, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    sequence_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    payload_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("uq_events_envelope_id", "envelope_id", unique=True),
        Index("ix_events_time", "time"),
        Index("ix_events_category", "category"),
        Index("ix_events_machine_id", "machine_id"),
        Index("ix_events_event_type_time", "event_type", "time"),
        Index("ix_events_session_id", "session_id"),
        Index("ix_events_strategy", "strategy"),
        Index("ix_events_symbol", "symbol"),
        Index("ix_events_severity_time", "severity", "time"),
    )
