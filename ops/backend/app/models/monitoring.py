"""ORM models for the monitoring.v1 receiver.

Shaped around the **LLS envelope**, not around a receiver-side idea of one. The
producer owns the contract; these tables exist to preserve what it sends.

Two rules drive the design:

* **Evidence is append-only and complete.** ``message_json`` holds the accepted
  message verbatim, so nothing the producer sent is lost merely because the
  receiver has no column for it. The denormalised columns beside it exist only so
  ordering and lookup do not require parsing JSON on every read — they are a
  cache of the message, never a substitute for it.
* **Two environments, never conflated.** ``source_environment`` is LLS's
  market-reality value (``live_trading``, ``offline_fixture``, …).
  ``receiver_deployment_environment`` is our own deployment tier, supplied by
  receiver configuration and ``UNKNOWN`` when not configured. Deriving one from
  the other would be an invented fact.

There is deliberately no ``stale_after`` column anywhere. monitoring.v1 has no
validity horizon; freshness is a state the source asserts.

Column types stay portable (no PostgreSQL-only types) so the same models run on
Postgres and on SQLite in tests.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, utcnow

#: Used when the receiver has not been told its own deployment tier. Never
#: inferred from the message — the producer does not know where we run.
UNKNOWN_DEPLOYMENT = "UNKNOWN"


class MonitoringEvidence(Base):
    """One accepted monitoring.v1 message, exactly as received.

    Append-only. ``message_json`` is the canonical request body verbatim, so
    every projection can be discarded and rebuilt from this table, and any field
    the producer adds in a future revision is still retained even before the
    receiver has a column for it.
    """

    __tablename__ = "monitoring_evidence"

    #: The producer's content address: ``mon1/<sha256 of canonical JSON without
    #: message_id>``. Verified by the receiver, never merely trusted. Primary key,
    #: so a duplicate delivery cannot create a second row even if the application
    #: logic were wrong.
    message_id: Mapped[str] = mapped_column(String(80), primary_key=True)

    #: Tenant partition identity.
    organisation_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)

    source_id: Mapped[str] = mapped_column(String(80), nullable=False)
    source_instance: Mapped[str] = mapped_column(String(80), nullable=False)

    #: Verbatim wire value. monitoring.v1 carries this as a decimal *string* and
    #: the ACK must echo it unchanged, so the string is what is stored.
    source_sequence: Mapped[str] = mapped_column(String(24), nullable=False)
    #: Parsed form, for ordering arithmetic only. Never echoed.
    sequence_ordinal: Mapped[int] = mapped_column(BigInteger, nullable=False)

    message_type: Mapped[str] = mapped_column(String(48), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)

    #: LLS market reality. One of offline_fixture / replay / offline_live_shaped /
    #: live_market_paper / broker_sandbox / live_trading / unknown.
    source_environment: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Our deployment tier, from receiver configuration. UNKNOWN when unset.
    receiver_deployment_environment: Mapped[str] = mapped_column(
        String(32), nullable=False, default=UNKNOWN_DEPLOYMENT
    )

    #: Producer clock. Distinct from received_at, which is ours.
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    #: Source-side qualifier objects, stored verbatim as JSON text. Not flattened
    #: into columns: their internal shape is the producer's business and
    #: extracting a subset here would quietly discard the rest.
    source_as_of_json: Mapped[str] = mapped_column(Text, nullable=False)
    coverage_json: Mapped[str] = mapped_column(Text, nullable=False)
    freshness_json: Mapped[str] = mapped_column(Text, nullable=False)
    trust_json: Mapped[str] = mapped_column(Text, nullable=False)
    #: An array of capture identifiers. Stored as the array it is, never
    #: collapsed into a LIVE/HISTORICAL enum.
    runtime_json: Mapped[str] = mapped_column(Text, nullable=False)

    #: Denormalised for filtering only; the authoritative values are in the JSON.
    freshness_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    trust_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    coverage_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    capture_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)

    #: SHA-256 of the whole request body, per the contract. Echoed in the ACK.
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    #: The complete message, canonical bytes decoded as text.
    message_json: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("ix_mon_evidence_org_seq", "organisation_id", "source_id", "source_instance", "sequence_ordinal"),
        Index("ix_mon_evidence_org_type", "organisation_id", "message_type", "generated_at"),
        Index("ix_mon_evidence_instance_seq", "source_id", "source_instance", "sequence_ordinal"),
        Index("ix_mon_evidence_type", "message_type", "generated_at"),
        Index("ix_mon_evidence_received_at", "received_at"),
        Index("ix_mon_evidence_capture", "capture_ref"),
    )


class MonitoringSequenceState(Base):
    """Ordered-acceptance state per publisher instance.

    monitoring.v1 requires ordered acceptance: the first message of an instance
    is sequence 1, and each subsequent message must be the next one. A gap or an
    unknown older sequence is refused with 409 and the last accepted state is
    retained.

    The gap counters here are **observability only**. They record that a refusal
    happened; they never make a refused message look accepted. Keeping the two
    apart is what lets operators see delivery trouble without the dashboard
    claiming to hold data it rejected.
    """

    __tablename__ = "monitoring_sequence_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organisation_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(80), nullable=False)
    source_instance: Mapped[str] = mapped_column(String(80), nullable=False)

    last_accepted_sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_accepted_message_id: Mapped[str] = mapped_column(String(80), nullable=False)

    accepted_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    #: Refused because the sequence skipped ahead.
    refused_gap_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    #: Refused because the sequence was older and not a known message.
    refused_old_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    #: JSON array of {"expected": n, "received": m, "at": iso} — operational
    #: visibility into refusals, bounded.
    observed_gaps: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("organisation_id", "source_id", "source_instance", name="uq_mon_sequence_instance"),
        Index("ix_mon_sequence_last_seen", "last_seen_at"),
    )


class MonitoringRawRequest(Base):
    """Original bytes of a request that produced quarantined material.

    Stored post-decompression and pre-parse — the last point at which the bytes
    are still exactly what the publisher sent. Kept only for quarantined traffic;
    accepted messages are already recoverable verbatim from
    ``MonitoringEvidence.message_json``.
    """

    __tablename__ = "monitoring_raw_requests"

    request_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organisation_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    #: The authenticated source, not the one claimed in the body. When a request
    #: is quarantined because its body is untrustworthy, the credential is the
    #: only identity worth recording.
    source_id: Mapped[str] = mapped_column(String(80), nullable=False)
    claimed_source_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    content_encoding: Mapped[str | None] = mapped_column(String(32), nullable=True)
    byte_length: Mapped[int] = mapped_column(Integer, nullable=False)
    body_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    body: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    __table_args__ = (Index("ix_mon_raw_received_at", "received_at"),)


class MonitoringQuarantine(Base):
    """A message the receiver could not safely accept.

    Distinct from ``ingest_dead_letters``, which records *agent-protocol*
    envelopes that failed to persist. Quarantine records monitoring.v1 messages
    that were readable as bytes but not acceptable as meaning: unsupported
    version, forged identity, malformed structure, unauthorised source.

    Quarantined material never enters a projection and is never shown to a
    dashboard viewer as monitoring data.
    """

    __tablename__ = "monitoring_quarantine"

    quarantine_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    organisation_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)

    #: Only where extractable — a message may be quarantined precisely because
    #: its identity or version could not be read.
    message_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    declared_message_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    computed_message_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_id: Mapped[str] = mapped_column(String(80), nullable=False)
    claimed_source_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_instance: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_sequence: Mapped[str | None] = mapped_column(String(24), nullable=True)
    schema_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    __table_args__ = (
        Index("ix_mon_quarantine_received_at", "received_at"),
        Index("ix_mon_quarantine_reason", "source_id", "reason"),
        Index("ix_mon_quarantine_request", "request_id"),
    )


class MonitoringProjection(Base):
    """The current view for one (source, message type, capture) — derived.

    Every column is reconstructible from ``monitoring_evidence`` by replaying it
    in sequence order. ``app.monitoring.projections.rebuild`` does exactly that,
    and a test asserts the rebuilt state is identical to the incrementally
    maintained one.

    The qualifier objects are copied across verbatim. Nothing is flattened,
    defaulted, or recomputed here — a projection that reinterpreted its source
    would be a second opinion the receiver is not entitled to have.
    """

    __tablename__ = "monitoring_projections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organisation_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)

    receiver_deployment_environment: Mapped[str] = mapped_column(
        String(32), nullable=False, default=UNKNOWN_DEPLOYMENT
    )
    source_id: Mapped[str] = mapped_column(String(80), nullable=False)
    message_type: Mapped[str] = mapped_column(String(48), nullable=False)
    #: ``payload.capture_ref`` where the message type carries one; empty string
    #: otherwise, so the unique constraint stays usable on every backend.
    capture_ref: Mapped[str] = mapped_column(String(160), nullable=False, default="")

    message_id: Mapped[str] = mapped_column(String(80), nullable=False)
    source_instance: Mapped[str] = mapped_column(String(80), nullable=False)
    source_sequence: Mapped[str] = mapped_column(String(24), nullable=False)
    sequence_ordinal: Mapped[int] = mapped_column(BigInteger, nullable=False)

    source_environment: Mapped[str] = mapped_column(String(32), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    source_as_of_json: Mapped[str] = mapped_column(Text, nullable=False)
    coverage_json: Mapped[str] = mapped_column(Text, nullable=False)
    freshness_json: Mapped[str] = mapped_column(Text, nullable=False)
    trust_json: Mapped[str] = mapped_column(Text, nullable=False)
    runtime_json: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "receiver_deployment_environment",
            "organisation_id",
            "source_id",
            "message_type",
            "capture_ref",
            name="uq_mon_projection_key",
        ),
        Index("ix_mon_projection_type", "receiver_deployment_environment", "organisation_id", "message_type"),
    )


class MonitoringAudit(Base):
    """Security-relevant receiver events.

    Ingestion attempts, authentication failures, refusals, quarantines, and
    administrative access. Never contains a credential: only the outcome and the
    source identity the credential mapped to.
    """

    __tablename__ = "monitoring_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organisation_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    remote_addr: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_mon_audit_at", "at"),
        Index("ix_mon_audit_action", "action", "outcome"),
    )


class EvidenceIsImmutable(RuntimeError):
    """Raised when anything attempts to rewrite stored evidence."""


@event.listens_for(MonitoringEvidence, "before_update", propagate=True)
def _block_evidence_update(_mapper, _connection, target: MonitoringEvidence) -> None:
    """Evidence is append-only — enforced here, not only by convention.

    A projection bug, a replay, or a well-meaning migration would otherwise be
    able to rewrite what the producer actually said. The forensic value of this
    table is that it cannot be edited after the fact.
    """
    raise EvidenceIsImmutable(
        "monitoring_evidence is append-only; attempted update of "
        f"message_id={target.message_id!r}. Corrections arrive as new messages."
    )


@event.listens_for(MonitoringEvidence, "before_delete", propagate=True)
def _block_evidence_delete(_mapper, _connection, target: MonitoringEvidence) -> None:
    raise EvidenceIsImmutable(
        "monitoring_evidence is append-only; attempted delete of "
        f"message_id={target.message_id!r}. Retention, if ever added, must be an "
        "explicit administrative job."
    )
