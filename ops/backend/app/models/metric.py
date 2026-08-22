"""Metric ORM model — narrow time-series for custom + host metrics.

A custom ``metric()`` is one row (name/value/unit). A host ``metrics``/
``heartbeat`` snapshot fans out into several rows (cpu, ram, disk, internet_ms,
broker_ping_ms, …) that share one ``envelope_id`` — hence the uniqueness guard
is on (envelope_id, name) rather than envelope_id alone.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class Metric(Base):
    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    envelope_id: Mapped[str | None] = mapped_column(String, nullable=True)

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    machine: Mapped[str] = mapped_column(String, default="", nullable=False)
    # Soft reference to machines.id (indexed; no hard FK — see Event model).
    machine_id: Mapped[str | None] = mapped_column(String, nullable=True)
    strategy: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    unit: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("envelope_id", "name", name="uq_metrics_envelope_name"),
        Index("ix_metrics_machine_time", "machine_id", "time"),
        Index("ix_metrics_name_time", "name", "time"),
    )
