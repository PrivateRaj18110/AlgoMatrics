"""System health snapshot ORM model — historical performance telemetry."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class SystemHealthSnapshot(Base):
    __tablename__ = "system_health_snapshots"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    machine_id: Mapped[str] = mapped_column(String, nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String, nullable=True)
    event_id: Mapped[str | None] = mapped_column(String, nullable=True)

    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    tick_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    tick_delay_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    queue_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    queue_wait_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    p95_latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    p99_latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    api_success_pct: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)
    signal_fill_rate_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    cpu_usage_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    memory_mb: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    status: Mapped[str] = mapped_column(String, default="STABLE", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_system_health_snapshots_machine_time", "machine_id", "timestamp_utc"),
        Index("ix_system_health_snapshots_time", "timestamp_utc"),
        Index("ix_system_health_snapshots_event_id", "event_id"),
    )
