"""Trading session ORM model.

Answers the question the 20-second heartbeat staleness check cannot: *when the
Google VM is off, what was the last trading session, and did we get all of it?*

Sessions are created lazily from whatever the agent reports. An agent that never
sends ``session_id`` simply produces no rows — the schema is ready ahead of the
Google-side change (Phase 2 task G6) and nothing here fabricates Google state.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class TradingSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Agent-supplied session key, e.g. "2026-08-09-NSE".
    session_id: Mapped[str] = mapped_column(String, nullable=False)
    machine_id: Mapped[str] = mapped_column(String, nullable=False)
    machine: Mapped[str] = mapped_column(String, default="", nullable=False)

    # "open" until an end_of_day envelope closes it.
    status: Mapped[str] = mapped_column(String, default="open", nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    event_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    trade_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("session_id", "machine_id", name="uq_sessions_session_machine"),
        Index("ix_sessions_machine_id", "machine_id"),
        Index("ix_sessions_last_event_at", "last_event_at"),
    )
