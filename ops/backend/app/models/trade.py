"""Trade ORM model — the persisted blotter (mirrors the ``Trade`` schema)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    envelope_id: Mapped[str | None] = mapped_column(String, nullable=True)

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    strategy: Mapped[str] = mapped_column(String, default="", nullable=False)
    machine: Mapped[str] = mapped_column(String, default="", nullable=False)
    # Soft reference to machines.id (indexed; no hard FK — see Event model).
    machine_id: Mapped[str | None] = mapped_column(String, nullable=True)
    broker: Mapped[str] = mapped_column(String, default="", nullable=False)
    account: Mapped[str] = mapped_column(String, default="", nullable=False)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    direction: Mapped[str] = mapped_column(String, nullable=False)
    # Raw lifecycle verb (open/close/modify/pending/cancelled/rejected); the
    # blotter `status` (open/closed/cancelled) is derived from it on write.
    action: Mapped[str | None] = mapped_column(String, nullable=True)
    entry: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    exit: Mapped[float | None] = mapped_column(Float, nullable=True)
    quantity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    pnl: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    duration_sec: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String, default="closed", nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("uq_trades_envelope_id", "envelope_id", unique=True),
        Index("ix_trades_time", "time"),
        Index("ix_trades_strategy", "strategy"),
        Index("ix_trades_symbol", "symbol"),
        Index("ix_trades_status", "status"),
        Index("ix_trades_machine_id", "machine_id"),
    )
