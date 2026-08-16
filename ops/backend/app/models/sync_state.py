"""Sync state ORM model — one row per (machine_id, agent_id).

This is the durable answer to "did we actually receive everything Google sent?".
The agent numbers its envelopes monotonically per agent instance
(``sequence_id``); the server records the highest number seen and counts the
holes. Without this, the two silent loss paths in the agent — drop-oldest queue
overflow and corrupt-row eviction (``raj_monitor/queue.py``) — are invisible: the
pipeline looks perfectly healthy while data is missing.

``sequence_id`` is **not** an idempotency key. ``ingest_dedup.envelope_id``
remains the only thing that decides whether an envelope is processed. Sequence
numbers are for *observability*: a gap is recorded, never a reason to reject.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow


class SyncState(Base):
    __tablename__ = "sync_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Soft reference to machines.id (no hard FK — telemetry may arrive before a
    # machine row exists, and ingestion must never fail on ordering).
    machine_id: Mapped[str] = mapped_column(String, nullable=False)
    machine: Mapped[str] = mapped_column(String, default="", nullable=False)
    agent_id: Mapped[str] = mapped_column(String, default="", nullable=False)

    # Highest sequence_id observed for this agent instance.
    last_sequence_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Event time of the newest envelope (agent clock), vs. last_batch_at below
    # which is server clock. Both matter: a replayed backlog has old event times
    # and a fresh batch time.
    last_event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_batch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Depth of the agent's own outbound queue, when it reports one. A rising
    # value with a healthy heartbeat means AWS is the bottleneck.
    queue_depth: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Observability counters.
    gap_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_gap_from: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_gap_to: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_gap_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    missing_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    accepted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Newest trading session this agent reported, if it sends one.
    session_id: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("machine_id", "agent_id", name="uq_sync_state_machine_agent"),
        Index("ix_sync_state_machine_id", "machine_id"),
        Index("ix_sync_state_last_batch_at", "last_batch_at"),
    )
