"""Read models for the monitoring.v1 API.

Every response carries the full provenance of what it shows: which source and
instance said it, the sequence, the content address, when the source generated
it, what it is as-of in the source's own terms, and when we received it. A
number without that context is exactly what this system exists to stop shipping.

Three rules the serialisers follow without exception:

* Producer objects — ``coverage``, ``freshness``, ``trust``, ``runtime``,
  ``source_as_of``, ``payload`` — are passed through **verbatim**. Nothing is
  flattened, defaulted, recomputed or stripped, including explicit nulls.
* ``runtime`` stays the array of capture identifiers it is. It is never
  collapsed into a LIVE/HISTORICAL label.
* The two environments are reported separately and never derived from each
  other: ``sourceEnvironment`` is the producer's market reality,
  ``receiverDeploymentEnvironment`` is ours.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

from app.models.monitoring import (
    MonitoringEvidence,
    MonitoringProjection,
    MonitoringQuarantine,
    MonitoringSequenceState,
)
from app.monitoring import freshness as freshness_module
from app.monitoring import sequence as seq


def iso(value: datetime | None) -> str | None:
    """UTC ISO-8601 with a Z suffix. None stays None — never epoch, never now."""
    if value is None:
        return None
    aware = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return aware.isoformat().replace("+00:00", "Z")


def _load(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return fallback


def projection_view(row: MonitoringProjection) -> dict[str, Any]:
    """One current-state row, with the producer's own qualifiers intact."""
    freshness_block = _load(row.freshness_json, {})
    return {
        "messageType": row.message_type,
        "captureRef": row.capture_ref or None,
        "source": {
            "sourceId": row.source_id,
            "sourceInstance": row.source_instance,
            # Echoed as the string the producer sent.
            "sourceSequence": row.source_sequence,
            "messageId": row.message_id,
        },
        # Market reality, from the producer.
        "sourceEnvironment": row.source_environment,
        # Our deployment tier, from receiver configuration. Never inferred.
        "receiverDeploymentEnvironment": row.receiver_deployment_environment,
        # The array of capture identifiers, unmodified.
        "runtime": _load(row.runtime_json, []),
        "time": {
            # The producer's own as-of object, verbatim.
            "sourceAsOf": _load(row.source_as_of_json, {}),
            "generatedAt": iso(row.generated_at),
            "receivedAt": iso(row.received_at),
        },
        # Asserted by the source. No horizon is evaluated anywhere.
        "freshness": freshness_module.read(freshness_block).as_dict(),
        "trust": _load(row.trust_json, {}),
        "coverage": _load(row.coverage_json, {}),
        "payload": _load(row.payload_json, {}),
    }


def evidence_view(row: MonitoringEvidence) -> dict[str, Any]:
    """One immutable received message, as stored."""
    return {
        "messageId": row.message_id,
        "messageType": row.message_type,
        "schemaVersion": row.schema_version,
        "source": {
            "sourceId": row.source_id,
            "sourceInstance": row.source_instance,
            "sourceSequence": row.source_sequence,
        },
        "sourceEnvironment": row.source_environment,
        "receiverDeploymentEnvironment": row.receiver_deployment_environment,
        "runtime": _load(row.runtime_json, []),
        "time": {
            "sourceAsOf": _load(row.source_as_of_json, {}),
            "generatedAt": iso(row.generated_at),
            "receivedAt": iso(row.received_at),
        },
        "freshness": _load(row.freshness_json, {}),
        "trust": _load(row.trust_json, {}),
        "coverage": _load(row.coverage_json, {}),
        "requestSha256": row.request_sha256,
        # The complete message the producer sent, unmodified.
        "message": _load(row.message_json, {}),
    }


def sequence_view(row: MonitoringSequenceState) -> dict[str, Any]:
    """Ordered-acceptance state, including refusals.

    ``refusedGapCount`` and ``refusedOldCount`` are observability. A refused
    message was never accepted and appears nowhere as data — these counters
    exist so an operator can see a publisher delivering out of order.
    """
    return {
        "sourceId": row.source_id,
        "sourceInstance": row.source_instance,
        "lastAcceptedSequence": str(row.last_accepted_sequence),
        "lastAcceptedMessageId": row.last_accepted_message_id,
        "acceptedCount": row.accepted_count,
        "duplicateCount": row.duplicate_count,
        "refusedGapCount": row.refused_gap_count,
        "refusedOldCount": row.refused_old_count,
        "observedRefusals": seq.load_gaps(row.observed_gaps),
        "firstSeenAt": iso(row.first_seen_at),
        "lastSeenAt": iso(row.last_seen_at),
    }


def quarantine_view(row: MonitoringQuarantine) -> dict[str, Any]:
    """Administrative view of material that never entered a projection."""
    return {
        "quarantineId": row.quarantine_id,
        "requestId": row.request_id,
        "reason": row.reason,
        "detail": row.detail,
        "sourceId": row.source_id,
        "claimedSourceId": row.claimed_source_id,
        "sourceInstance": row.source_instance,
        "sourceSequence": row.source_sequence,
        "schemaVersion": row.schema_version,
        "declaredMessageId": row.declared_message_id,
        "computedMessageId": row.computed_message_id,
        "requestSha256": row.request_sha256,
        "receivedAt": iso(row.received_at),
    }
