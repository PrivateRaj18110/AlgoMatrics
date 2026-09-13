"""The monitoring.v1 receiver.

One message per request, as the contract defines. There is no batch wrapper,
because monitoring.v1 does not have one and forcing the producer's protocol into
the retired batch shape would be inventing transport semantics.

Validation order, and nothing may skip ahead of it:

    authentication            (router dependency)
    request-size validation   ─┐
    strict JSON parsing        │
    structural limits          │
    version validation         │
    JSON Schema validation     │ this module
    message identity           │
    sequence validation        │
    duplicate determination    │
    immutable evidence        ─┘
    projection
    ACK

Two orderings inside that are load-bearing and worth stating:

* **Duplicate is decided after the sequence is parsed but before the ordered-
  acceptance rule is applied.** The contract requires a previously accepted
  message to be acknowledged again even after later sequences have arrived; if
  ordering ran first, a legitimate redelivery would be refused as an old
  sequence.
* **Evidence is committed before the ACK is returned.** The producer deletes
  from its durable queue on a successful ACK, so acknowledging before the write
  is durable would lose data on a crash between the two.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies.monitoring_auth import MonitoringPrincipal
from app.core.config import get_settings
from app.database.session import database_enabled, get_sessionmaker
from app.models.monitoring import (
    UNKNOWN_DEPLOYMENT,
    MonitoringAudit,
    MonitoringEvidence,
    MonitoringQuarantine,
    MonitoringRawRequest,
    MonitoringSequenceState,
)
from app.monitoring import contract, freshness, projections
from app.monitoring import sequence as seq

ACK_SCHEMA_VERSION = "monitoring.ack.v1"

ACCEPTED = "accepted"
DUPLICATE = "duplicate"

#: How much of a refused request body is kept verbatim.
#:
#: Set *above* the contract's own 1 MiB request ceiling, on purpose. A message
#: refused for being marginally too large is the case an investigator most wants
#: to see whole — how far over, and what was in the tail — and a cap set exactly
#: at the limit would clip precisely that. The headroom keeps every realistic
#: near-limit refusal intact while still bounding the deliberately oversized
#: traffic this exists to stop.
#:
#: ``byte_length`` and ``body_sha256`` always describe the **whole** body, so
#: truncation never hides how much arrived or which bytes they were.
MAX_PRESERVED_REQUEST_BYTES = contract.LIMITS.request_bytes + (64 * 1024)


# --------------------------------------------------------------------------- #
# Refusals. Each carries the HTTP status the contract's cases expect.
# --------------------------------------------------------------------------- #
class ReceiverRefusal(Exception):
    """A message the receiver will not accept. Never silent."""

    status_code = 400
    reason = "refused"

    def __init__(self, detail: str, *, quarantine_id: str | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.quarantine_id = quarantine_id


class MalformedRequest(ReceiverRefusal):
    """Unparseable, duplicate keys, or non-finite numbers."""

    status_code = 400
    reason = "malformed"


class StructuralLimitExceeded(ReceiverRefusal):
    """Over a normative size, depth, node, array or string limit."""

    status_code = 413
    reason = "structural_limit"


class UnsupportedVersion(ReceiverRefusal):
    """A schema_version this build does not implement. Quarantined, never guessed."""

    status_code = 422
    reason = "schema_version_unsupported"


class SchemaInvalid(ReceiverRefusal):
    """Does not satisfy the canonical schema."""

    status_code = 422
    reason = "schema_invalid"


class IdentityInvalid(ReceiverRefusal):
    """The declared message_id is not the content address of the body.

    400 rather than 409: the producer's own cases accept 400 both for a forged
    identity and for a reused identity with changed bytes, and under content
    addressing those are the same defect — the label does not match the content.
    """

    status_code = 400
    reason = "identity_mismatch"


class DigestMismatch(ReceiverRefusal):
    """The X-Monitoring-SHA256 header does not match the request bytes."""

    status_code = 400
    reason = "request_digest_mismatch"


class SourceNotAuthorized(ReceiverRefusal):
    """The body claims a source the credential does not cover."""

    status_code = 403
    reason = "source_not_authorized"


class SequenceRefused(ReceiverRefusal):
    """A gap or an unknown older sequence. The contract's 409."""

    status_code = 409
    reason = "sequence_refused"


class StorageUnavailable(RuntimeError):
    """The receiver cannot durably store right now — HTTP 503."""


# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class Acknowledgement:
    """The exact ``monitoring.ack.v1`` body, and nothing else.

    The producer validates every field of this and treats a mismatch as a failed
    delivery, so the shape is fixed: five keys, ``source_sequence`` echoed as the
    string that arrived.
    """

    message_id: str
    sha256: str
    source_sequence: str
    status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ACK_SCHEMA_VERSION,
            "message_id": self.message_id,
            "sha256": self.sha256,
            "source_sequence": self.source_sequence,
            "status": self.status,
        }


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def ingest_message(
    raw_body: bytes,
    principal: MonitoringPrincipal,
    *,
    declared_digest: str | None = None,
    content_encoding: str | None = None,
    now: datetime | None = None,
) -> Acknowledgement:
    """Run the full receiver pipeline over one monitoring.v1 message."""
    received_at = now or datetime.now(UTC)

    if not database_enabled():
        # Without durable storage the receiver cannot honour idempotency,
        # ordering or evidence retention. A 503 keeps the producer's queue.
        raise StorageUnavailable(
            "monitoring.v1 storage is not configured; the receiver will not "
            "acknowledge messages it cannot durably store"
        )

    try:
        session: Session = get_sessionmaker()()
    except DBAPIError as exc:
        # The database is unreachable. Never an acknowledgement.
        raise StorageUnavailable(
            f"monitoring.v1 storage is unavailable: {exc.__class__.__name__}"
        ) from exc

    try:
        ack = _ingest(session, raw_body, principal, received_at, declared_digest, content_encoding)
        # Committed before the caller can return the ACK.
        session.commit()
        return ack
    except ReceiverRefusal:
        # Quarantine rows, preserved bytes and the audit entry are exactly what
        # makes a refusal investigable. Rolling them back would leave a rejected
        # upload with no record that it ever happened.
        try:
            session.commit()
        except DBAPIError:
            # The refusal still stands; only its forensic record is lost.
            session.rollback()
        raise
    except DBAPIError as exc:
        # Any database error that prevented the write. The question the producer
        # needs answered is only ever "was this message durably stored?", and
        # when the database refused for *any* reason the answer is no — so it
        # gets the contract's retryable 503 rather than an unhandled 500.
        #
        # Deliberately wider than a connection failure. Staging measurement
        # found a read-only database surfacing as `InternalError` and a revoked
        # grant as `ProgrammingError`, neither of which is an `OperationalError`;
        # both left the producer guessing at a 500. A replica promoted to
        # read-only, a failed-over primary, a revoked grant and a full volume are
        # the same event as far as this decision goes.
        session.rollback()
        raise StorageUnavailable(
            f"monitoring.v1 storage refused the write: {exc.__class__.__name__}"
        ) from exc
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def _ingest(
    session: Session,
    raw_body: bytes,
    principal: MonitoringPrincipal,
    received_at: datetime,
    declared_digest: str | None,
    content_encoding: str | None,
) -> Acknowledgement:
    settings = get_settings()
    deployment = _deployment_environment(settings)
    digest = contract.request_digest(raw_body)

    def refuse(exc: ReceiverRefusal, **fields: Any) -> ReceiverRefusal:
        _preserve_request(session, raw_body, principal, received_at, content_encoding, fields)
        quarantine_id = _quarantine(
            session,
            request_id=principal.request_id,
            source_id=principal.source_id,
            reason=exc.reason,
            detail=exc.detail[:2000],
            received_at=received_at,
            request_sha256=digest,
            **fields,
        )
        _audit(session, "monitoring.ingest", exc.reason, principal, exc.detail[:256])
        exc.quarantine_id = quarantine_id
        return exc

    # --- request-size validation -----------------------------------------
    if len(raw_body) > contract.LIMITS.request_bytes:
        raise refuse(
            StructuralLimitExceeded(
                f"{len(raw_body)} bytes exceeds the {contract.LIMITS.request_bytes} byte limit"
            )
        )

    # --- request digest, when the sender declared one ---------------------
    if declared_digest and declared_digest.strip().lower() != digest:
        raise refuse(DigestMismatch("X-Monitoring-SHA256 does not match the request bytes"))

    # --- strict JSON parsing ---------------------------------------------
    try:
        document = contract.parse_message(raw_body)
    except contract.DuplicateKeyError as exc:
        raise refuse(MalformedRequest(f"duplicate object key: {exc}")) from exc
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise refuse(MalformedRequest(f"unparseable request body: {exc}")) from exc
    if not isinstance(document, dict):
        raise refuse(MalformedRequest("the request body must be a JSON object"))

    claimed_source = (
        document.get("source_id") if isinstance(document.get("source_id"), str) else None
    )
    context: dict[str, Any] = {
        "claimed_source_id": claimed_source,
        "declared_message_id": document.get("message_id")
        if isinstance(document.get("message_id"), str)
        else None,
        "source_instance": document.get("source_instance")
        if isinstance(document.get("source_instance"), str)
        else None,
        "source_sequence": document.get("source_sequence")
        if isinstance(document.get("source_sequence"), str)
        else None,
        "schema_version": document.get("schema_version")
        if isinstance(document.get("schema_version"), str)
        else None,
    }

    # --- structural limits ------------------------------------------------
    violation = contract.check_limits(document)
    if violation is not None:
        raise refuse(StructuralLimitExceeded(violation.detail), **context)

    # --- version validation ----------------------------------------------
    version = contract.classify_version(document.get("schema_version"))
    if not version.accepted:
        raise refuse(
            UnsupportedVersion(f"{version.reason}: {version.note or version.raw}"), **context
        )

    # --- JSON Schema validation -------------------------------------------
    errors = contract.schema_errors(document)
    if errors:
        raise refuse(SchemaInvalid(errors[0]), **context)

    # --- message identity --------------------------------------------------
    computed = contract.message_identity(document)
    if document["message_id"] != computed:
        raise refuse(
            IdentityInvalid(
                "declared message_id is not the content address of this body; "
                "the label and the content disagree"
            ),
            **{**context, "computed_message_id": computed},
        )
    message_id = document["message_id"]

    # --- source authorisation (body vs credential) -------------------------
    if not principal.authorizes_source(document["source_id"]):
        raise refuse(
            SourceNotAuthorized("credential is not authorized for this source_id"), **context
        )

    # --- sequence validation (format) --------------------------------------
    source_sequence = document["source_sequence"]
    ordinal = contract.parse_sequence(source_sequence)
    if ordinal is None:
        raise refuse(SchemaInvalid(f"unreadable source_sequence {source_sequence!r}"), **context)

    source_id = document["source_id"]
    source_instance = document["source_instance"]

    # --- serialise this publisher instance ---------------------------------
    # Everything below reads the instance's accepted state and then writes it.
    # Under PostgreSQL's READ COMMITTED that read-then-write is a race: two
    # concurrent deliveries for the same instance both observe the same
    # "last accepted" value, both decide, and both write. SQLite hides this
    # entirely because it serialises writers.
    _lock_instance(session, source_id, source_instance)

    # --- duplicate determination -------------------------------------------
    # Before the ordering rule, deliberately: the contract requires a previously
    # accepted message to be acknowledged again even after later sequences.
    existing = session.get(MonitoringEvidence, message_id)
    if existing is not None:
        _bump_duplicate(session, source_id, source_instance, received_at)
        _audit(session, "monitoring.ingest", DUPLICATE, principal, message_id)
        return Acknowledgement(
            message_id=message_id,
            sha256=existing.request_sha256,
            source_sequence=existing.source_sequence,
            status=DUPLICATE,
        )

    # --- ordered acceptance -------------------------------------------------
    state = session.execute(
        select(MonitoringSequenceState).where(
            MonitoringSequenceState.source_id == source_id,
            MonitoringSequenceState.source_instance == source_instance,
        )
    ).scalar_one_or_none()

    decision = seq.decide(
        received=ordinal, last_accepted=state.last_accepted_sequence if state else None
    )
    if not decision.accepted:
        _record_refusal(session, state, decision, received_at)
        _audit(session, "monitoring.ingest", decision.action, principal, decision.detail[:256])
        # Not quarantined: the message is well-formed and may become acceptable
        # once the producer delivers the messages before it. Quarantining it
        # would imply it was defective, which it is not.
        raise SequenceRefused(decision.detail)

    # --- immutable evidence -------------------------------------------------
    evidence = _build_evidence(document, digest, received_at, deployment, ordinal)
    session.add(evidence)
    try:
        session.flush()
    except IntegrityError:
        # Lost a race with a concurrent delivery of the same content address.
        # The other writer stored it; this is a duplicate, not a failure.
        session.rollback()
        stored = session.get(MonitoringEvidence, message_id)
        if stored is None:  # pragma: no cover - only on a genuine storage fault
            raise
        return Acknowledgement(
            message_id=message_id,
            sha256=stored.request_sha256,
            source_sequence=stored.source_sequence,
            status=DUPLICATE,
        )

    _advance_sequence(session, state, source_id, source_instance, ordinal, message_id, received_at)

    # --- projection ---------------------------------------------------------
    projections.apply(session, evidence, document)
    session.flush()

    _audit(session, "monitoring.ingest", ACCEPTED, principal, message_id)
    return Acknowledgement(
        message_id=message_id,
        sha256=digest,
        source_sequence=source_sequence,
        status=ACCEPTED,
    )


# --------------------------------------------------------------------------- #
# Persistence helpers
# --------------------------------------------------------------------------- #
def _lock_instance(session: Session, source_id: str, source_instance: str) -> None:
    """Hold an exclusive lock on one ``(source_id, source_instance)`` until commit.

    Ordered acceptance is a read-then-write over the instance's accepted state:
    read the last accepted sequence, decide, write the new one. Two concurrent
    deliveries for the same instance can both read the same value before either
    writes, and then both act on it — accepting the same sequence twice, or
    racing to create the instance's first state row and surfacing a raw
    ``IntegrityError`` to the producer.

    A transaction-scoped advisory lock is the smallest fix that closes both.
    It costs one statement, it is released automatically on commit or rollback
    even if the process dies, and it constrains nothing the contract did not
    already constrain: monitoring.v1 requires an instance's messages to be
    accepted in order, so serialising *one instance* removes no concurrency
    that was ever permitted. Different instances and different sources stay
    fully parallel.

    A no-op on SQLite, which has no advisory locks and does not need them — it
    serialises writers at the database level.
    """
    bind = session.get_bind()
    if bind.dialect.name != "postgresql":
        return
    # A stable 64-bit signed key for the pair. The lock namespace is shared
    # process-wide, so the key must not collide with another subsystem's:
    # hashing the two identifiers together makes an accidental collision as
    # unlikely as a hash collision.
    digest = hashlib.blake2b(
        f"monitoring.v1\x00{source_id}\x00{source_instance}".encode(), digest_size=8
    ).digest()
    session.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": int.from_bytes(digest, "big", signed=True)},
    )


def _deployment_environment(settings: Any) -> str:
    """Our own deployment tier, from receiver configuration only.

    Never derived from the message. LLS's ``environment`` describes market
    reality and says nothing about where this receiver runs; mapping one to the
    other would be an invented fact.
    """
    configured = (getattr(settings, "monitoring_deployment_environment", "") or "").strip()
    return configured or UNKNOWN_DEPLOYMENT


def _build_evidence(
    document: dict[str, Any],
    digest: str,
    received_at: datetime,
    deployment: str,
    ordinal: int,
) -> MonitoringEvidence:
    """Store the message verbatim, plus a cache of fields used for lookup.

    Everything the producer sent survives in ``message_json`` — including any
    field this build has no column for.
    """
    coverage = document.get("coverage") or {}
    trust = document.get("trust") or {}
    freshness_block = document.get("freshness") or {}
    payload = document.get("payload") or {}

    return MonitoringEvidence(
        message_id=document["message_id"],
        source_id=document["source_id"],
        source_instance=document["source_instance"],
        # Verbatim. The ACK echoes this string, never a re-rendered form.
        source_sequence=document["source_sequence"],
        sequence_ordinal=ordinal,
        message_type=document["message_type"],
        schema_version=document["schema_version"],
        source_environment=document["environment"],
        receiver_deployment_environment=deployment,
        generated_at=_parse_ts(document["generated_at"]) or received_at,
        received_at=received_at,
        source_as_of_json=_dump(document.get("source_as_of")),
        coverage_json=_dump(coverage),
        freshness_json=_dump(freshness_block),
        trust_json=_dump(trust),
        runtime_json=_dump(document.get("runtime")),
        freshness_source=freshness_block.get("source")
        if isinstance(freshness_block.get("source"), str)
        else None,
        trust_status=trust.get("status") if isinstance(trust.get("status"), str) else None,
        coverage_status=coverage.get("status") if isinstance(coverage.get("status"), str) else None,
        capture_ref=payload.get("capture_ref")
        if isinstance(payload.get("capture_ref"), str)
        else None,
        request_sha256=digest,
        message_json=contract.canonical_json(document).decode("utf-8"),
    )


def _advance_sequence(
    session: Session,
    state: MonitoringSequenceState | None,
    source_id: str,
    source_instance: str,
    ordinal: int,
    message_id: str,
    received_at: datetime,
) -> None:
    if state is None:
        session.add(
            MonitoringSequenceState(
                source_id=source_id,
                source_instance=source_instance,
                last_accepted_sequence=ordinal,
                last_accepted_message_id=message_id,
                accepted_count=1,
                first_seen_at=received_at,
                last_seen_at=received_at,
                observed_gaps="[]",
            )
        )
    else:
        state.last_accepted_sequence = ordinal
        state.last_accepted_message_id = message_id
        state.accepted_count += 1
        state.last_seen_at = received_at
    session.flush()


def _record_refusal(
    session: Session,
    state: MonitoringSequenceState | None,
    decision: seq.SequenceDecision,
    received_at: datetime,
) -> None:
    """Count and record a refusal for operators — without accepting anything."""
    if state is None:
        # Nothing accepted yet for this instance, so there is no state row to
        # advance. The audit entry carries the refusal.
        return
    if decision.action == "refuse_gap":
        state.refused_gap_count += 1
    else:
        state.refused_old_count += 1
    state.observed_gaps = seq.record_gap(
        state.observed_gaps, decision, received_at.isoformat().replace("+00:00", "Z")
    )
    state.last_seen_at = received_at
    session.flush()


def _bump_duplicate(
    session: Session, source_id: str, source_instance: str, received_at: datetime
) -> None:
    state = session.execute(
        select(MonitoringSequenceState).where(
            MonitoringSequenceState.source_id == source_id,
            MonitoringSequenceState.source_instance == source_instance,
        )
    ).scalar_one_or_none()
    if state is not None:
        state.duplicate_count += 1
        state.last_seen_at = received_at
        session.flush()


def _preserve_request(
    session: Session,
    raw_body: bytes,
    principal: MonitoringPrincipal,
    received_at: datetime,
    content_encoding: str | None,
    fields: dict[str, Any],
) -> None:
    """Keep the original bytes of a refused request, post-decompression.

    Bounded. Staging measurement showed why: a request refused for being too
    large was still stored in full, so 27 rejected requests wrote 233 MB of
    evidence for messages the receiver had already refused — and a gzip body
    made that a 1000:1 amplification. A refusal path that costs more storage
    than an acceptance is a way to fill the database with rejected traffic.

    What is stored is a bounded prefix, plus the true ``byte_length`` and a
    SHA-256 over the **whole** body. The digest is what makes the record
    forensically useful: it identifies the exact bytes, so a submitted sample
    can still be proven to be the one that was refused. Keeping the remaining
    megabytes adds nothing an investigator can use that the prefix and the
    digest do not already give them.
    """
    if session.get(MonitoringRawRequest, principal.request_id) is not None:
        return
    session.add(
        MonitoringRawRequest(
            request_id=principal.request_id,
            source_id=principal.source_id,
            claimed_source_id=fields.get("claimed_source_id"),
            received_at=received_at,
            content_encoding=content_encoding,
            # The true length, even when the stored body is truncated.
            byte_length=len(raw_body),
            # Over the whole body, never over the truncated prefix.
            body_sha256=hashlib.sha256(raw_body).hexdigest(),
            body=raw_body[:MAX_PRESERVED_REQUEST_BYTES],
        )
    )
    session.flush()


def _quarantine(
    session: Session,
    *,
    request_id: str,
    source_id: str,
    reason: str,
    detail: str | None,
    received_at: datetime,
    request_sha256: str | None = None,
    **fields: Any,
) -> str:
    quarantine_id = uuid.uuid4().hex
    session.add(
        MonitoringQuarantine(
            quarantine_id=quarantine_id,
            request_id=request_id,
            source_id=source_id,
            reason=reason,
            detail=detail,
            received_at=received_at,
            request_sha256=request_sha256,
            message_id=fields.get("declared_message_id"),
            declared_message_id=fields.get("declared_message_id"),
            computed_message_id=fields.get("computed_message_id"),
            claimed_source_id=fields.get("claimed_source_id"),
            source_instance=fields.get("source_instance"),
            source_sequence=fields.get("source_sequence"),
            schema_version=fields.get("schema_version"),
        )
    )
    session.flush()
    return quarantine_id


def _audit(
    session: Session, action: str, outcome: str, principal: MonitoringPrincipal, detail: str | None
) -> None:
    session.add(
        MonitoringAudit(
            action=action,
            outcome=outcome,
            source_id=principal.source_id,
            request_id=principal.request_id,
            remote_addr=principal.remote_addr,
            detail=detail,
        )
    )


def _dump(value: Any) -> str:
    return contract.canonical_json(value if value is not None else {}).decode("utf-8")


def _parse_ts(value: Any) -> datetime | None:
    """Parse a contract timestamp. None stays None — never defaulted to now."""
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


# Re-exported so callers do not have to import the freshness module directly
# when they only need the reader.
read_freshness = freshness.read
