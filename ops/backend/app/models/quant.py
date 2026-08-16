"""Durable AWS-side quant analytics reports.

Reports are derived from finalized EOD datasets. They are intentionally
separate from trading/broker/risk tables: this model stores observational
analytics only and has no control-path fields.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class QuantReport(Base):
    __tablename__ = "quant_reports"

    report_id: Mapped[str] = mapped_column(String, primary_key=True)
    dataset_id: Mapped[str] = mapped_column(String, nullable=False)
    machine_id: Mapped[str] = mapped_column(String, nullable=False)
    trading_date: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="READY", nullable=False)

    coverage_json: Mapped[str] = mapped_column(Text, nullable=False)
    trade_metrics_json: Mapped[str] = mapped_column(Text, nullable=False)
    market_replay_json: Mapped[str] = mapped_column(Text, nullable=False)
    analytics_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    warnings_json: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_quant_reports_dataset_id", "dataset_id"),
        Index("ix_quant_reports_machine_id", "machine_id"),
        Index("ix_quant_reports_trading_date", "trading_date"),
        Index("ix_quant_reports_created_at", "created_at"),
    )
