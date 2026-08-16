"""Dead-letter ORM model — envelopes that could not be processed.

Replaces the previous ``except Exception: continue`` in ``handle_batch``, which
dropped malformed envelopes with no record and still reported the whole batch as
processed. A monitoring system that silently discards the events it cannot parse
is worse than one that is simply down, because it looks healthy.

Only *permanent* failures land here — a malformed or unroutable envelope that
would fail identically on every redelivery. Transient failures (database
unavailable) must NOT be dead-lettered: they are reported back to the agent so
its durable queue retries. See ``agent_service._dispatch``.

The stored ``payload_preview`` is a truncated repr for debugging. Envelope
payloads carry trading telemetry, never credentials, and the preview is capped
so a large market payload cannot bloat the table.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow

# Upper bound on the debugging preview kept per dead-lettered envelope.
PAYLOAD_PREVIEW_LIMIT = 2000


class DeadLetter(Base):
    __tablename__ = "ingest_dead_letters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    envelope_id: Mapped[str | None] = mapped_column(String, nullable=True)
    kind: Mapped[str | None] = mapped_column(String, nullable=True)
    machine: Mapped[str | None] = mapped_column(String, nullable=True)
    machine_id: Mapped[str | None] = mapped_column(String, nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String, nullable=True)
    strategy: Mapped[str | None] = mapped_column(String, nullable=True)
    sequence_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    reason: Mapped[str] = mapped_column(String, nullable=False)
    error_type: Mapped[str | None] = mapped_column(String, nullable=True)
    payload_preview: Mapped[str | None] = mapped_column(Text, nullable=True)

    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        Index("ix_dead_letters_received_at", "received_at"),
        Index("ix_dead_letters_machine_id", "machine_id"),
        Index("ix_dead_letters_envelope_id", "envelope_id"),
    )
