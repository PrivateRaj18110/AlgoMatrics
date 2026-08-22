"""Machine (host) ORM model — the live counterpart of the ``Machine`` schema."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class Machine(Base):
    __tablename__ = "machines"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    location: Mapped[str] = mapped_column(String, default="", nullable=False)
    provider: Mapped[str] = mapped_column(String, default="", nullable=False)
    status: Mapped[str] = mapped_column(String, default="online", nullable=False)

    cpu: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    ram: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    disk: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    internet_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    broker_ping_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    python_status: Mapped[str] = mapped_column(String, default="online", nullable=False)
    uptime_sec: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    strategy_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Set when a real Local Agent registers this host (vs a seeded demo row).
    live: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String, nullable=True)
    agent_version: Mapped[str | None] = mapped_column(String, nullable=True)

    # Phase 3 current-state fields. Historical telemetry remains in events /
    # logs / trades / metrics; this row is only the bounded "latest known state"
    # the dashboard can answer quickly without scanning event history.
    hostname: Mapped[str] = mapped_column(String, default="", nullable=False)
    environment: Mapped[str] = mapped_column(String, default="", nullable=False)
    last_event: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_trade: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_successful_upload: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    queue_depth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    oldest_pending_age_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    transport_state: Mapped[str | None] = mapped_column(String, nullable=True)
    current_session_id: Mapped[str | None] = mapped_column(String, nullable=True)
    trading_process_state: Mapped[str | None] = mapped_column(String, nullable=True)
    last_eod_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_eod_status: Mapped[str | None] = mapped_column(String, nullable=True)
    recovery_state: Mapped[str | None] = mapped_column(String, nullable=True)
    last_recovery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    events_recovered: Mapped[int | None] = mapped_column(Integer, nullable=True)
    eod_backlog: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_machines_status", "status"),
        Index("ix_machines_live", "live"),
        Index("ix_machines_last_heartbeat", "last_heartbeat"),
        Index("ix_machines_current_session_id", "current_session_id"),
        Index("ix_machines_last_successful_upload", "last_successful_upload"),
    )
