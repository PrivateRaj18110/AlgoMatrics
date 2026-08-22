"""Idempotency guard — one row per processed Envelope.

The agent delivers at-least-once from its durable queue, so the same envelope
can arrive more than once. ``_dispatch`` inserts the envelope id here first
(``ON CONFLICT DO NOTHING``); a no-op insert means the envelope was already
processed and is skipped entirely — no duplicate rows, no duplicate broadcast.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class IngestDedup(Base):
    __tablename__ = "ingest_dedup"

    envelope_id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
