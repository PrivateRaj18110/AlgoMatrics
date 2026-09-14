"""Deriving the current view from immutable evidence.

A projection answers "what is the latest the producer told us about this". It is
derived, disposable and rebuildable: :func:`rebuild` drops every projection row
and replays ``monitoring_evidence``, and a test asserts the result is identical
to the incrementally maintained one. That property is what makes a projection bug
recoverable rather than a permanent corruption of history.

Nothing here interprets monitoring meaning. Projection is routing and ordering —
which row does this message update, and is it newer than what that row holds. The
producer's qualifier objects and payload are copied across **verbatim**.

Keyed by ``(receiver_deployment_environment, source_id, message_type,
capture_ref)``. That follows the producer's own model: ``message_type`` is the
contract's discriminator, and ``capture_ref`` distinguishes observations of
different captures, which are genuinely different subjects rather than successive
states of one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.monitoring import MonitoringEvidence, MonitoringProjection


@dataclass(frozen=True, slots=True)
class ProjectionOutcome:
    """What applying one piece of evidence did to the current view."""

    #: "applied" | "superseded"
    action: str
    capture_ref: str


def capture_ref_for(document: dict[str, Any]) -> str:
    """``payload.capture_ref`` where the message type carries one.

    Empty string otherwise, so the unique constraint stays usable on every
    database backend — NULLs do not compare equal in a unique index.
    """
    payload = document.get("payload") or {}
    value = payload.get("capture_ref")
    return value if isinstance(value, str) else ""


def apply(
    session: Session, evidence: MonitoringEvidence, document: dict[str, Any]
) -> ProjectionOutcome:
    """Move the current view forward if this evidence is newer than what it holds."""
    capture_ref = capture_ref_for(document)
    existing = session.execute(
        select(MonitoringProjection).where(
            MonitoringProjection.receiver_deployment_environment
            == evidence.receiver_deployment_environment,
            MonitoringProjection.organisation_id == evidence.organisation_id,
            MonitoringProjection.source_id == evidence.source_id,
            MonitoringProjection.message_type == evidence.message_type,
            MonitoringProjection.capture_ref == capture_ref,
        )
    ).scalar_one_or_none()

    payload_json = _dump(document.get("payload"))

    if existing is None:
        session.add(
            MonitoringProjection(
                receiver_deployment_environment=evidence.receiver_deployment_environment,
                organisation_id=evidence.organisation_id,
                source_id=evidence.source_id,
                message_type=evidence.message_type,
                capture_ref=capture_ref,
                message_id=evidence.message_id,
                source_instance=evidence.source_instance,
                source_sequence=evidence.source_sequence,
                sequence_ordinal=evidence.sequence_ordinal,
                source_environment=evidence.source_environment,
                generated_at=evidence.generated_at,
                received_at=evidence.received_at,
                source_as_of_json=evidence.source_as_of_json,
                coverage_json=evidence.coverage_json,
                freshness_json=evidence.freshness_json,
                trust_json=evidence.trust_json,
                runtime_json=evidence.runtime_json,
                payload_json=payload_json,
            )
        )
        return ProjectionOutcome(action="applied", capture_ref=capture_ref)

    if _compare(existing, evidence) != "newer":
        return ProjectionOutcome(action="superseded", capture_ref=capture_ref)

    existing.message_id = evidence.message_id
    existing.source_instance = evidence.source_instance
    existing.source_sequence = evidence.source_sequence
    existing.sequence_ordinal = evidence.sequence_ordinal
    existing.source_environment = evidence.source_environment
    existing.generated_at = evidence.generated_at
    existing.received_at = evidence.received_at
    existing.source_as_of_json = evidence.source_as_of_json
    existing.coverage_json = evidence.coverage_json
    existing.freshness_json = evidence.freshness_json
    existing.trust_json = evidence.trust_json
    existing.runtime_json = evidence.runtime_json
    existing.payload_json = payload_json
    return ProjectionOutcome(action="applied", capture_ref=capture_ref)


def _compare(existing: MonitoringProjection, incoming: MonitoringEvidence) -> str:
    """Is ``incoming`` newer than what the projection holds?

    Within one publisher instance ``source_sequence`` orders absolutely — the
    receiver only ever accepts them in order, so a higher sequence is strictly
    later. Across instances sequence numbers restart and are not comparable, so
    the producer's ``generated_at`` decides.

    Arrival time is never consulted.
    """
    if incoming.source_instance == existing.source_instance:
        if incoming.sequence_ordinal > existing.sequence_ordinal:
            return "newer"
        return "older_or_same"

    incoming_at = _aware(incoming.generated_at)
    existing_at = _aware(existing.generated_at)
    return "newer" if incoming_at > existing_at else "older_or_same"


def rebuild(
    session: Session,
    *,
    deployment_environment: str | None = None,
    organisation_id: UUID | None = None,
) -> int:
    """Drop and replay every projection from stored evidence.

    Deterministic and idempotent: replay order is the producer's order
    (``generated_at``, then instance, then sequence), never insertion order or
    arrival time, so the same evidence always yields the same projection.

    Evidence itself is never touched.
    """
    query = select(MonitoringProjection)
    if deployment_environment is not None:
        query = query.where(
            MonitoringProjection.receiver_deployment_environment == deployment_environment
        )
    if organisation_id is not None:
        query = query.where(MonitoringProjection.organisation_id == organisation_id)
    for row in session.execute(query).scalars():
        session.delete(row)
    session.flush()

    evidence_query = select(MonitoringEvidence)
    if deployment_environment is not None:
        evidence_query = evidence_query.where(
            MonitoringEvidence.receiver_deployment_environment == deployment_environment
        )
    if organisation_id is not None:
        evidence_query = evidence_query.where(MonitoringEvidence.organisation_id == organisation_id)
    evidence_query = evidence_query.order_by(
        MonitoringEvidence.generated_at,
        MonitoringEvidence.source_instance,
        MonitoringEvidence.sequence_ordinal,
    )

    applied = 0
    for evidence in session.execute(evidence_query).scalars():
        document = json.loads(evidence.message_json)
        if apply(session, evidence, document).action == "applied":
            applied += 1
        session.flush()
    return applied


def _dump(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True, separators=(",", ":"))


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
