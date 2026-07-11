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

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_machines_status", "status"),
        Index("ix_machines_live", "live"),
        Index("ix_machines_last_heartbeat", "last_heartbeat"),
    )
