"""Tamper-evident hashing for the immutable audit log.

Each audit entry stores the hash of the previous entry (``prev_hash``) and its
own hash (``entry_hash``) computed over a canonical serialization of its fields
plus ``prev_hash``. This forms a hash chain: altering or removing any historical
entry invalidates every subsequent ``entry_hash``, which the verifier detects.

The functions here are pure and deterministic so they can be unit tested without
a database and reused verbatim by the Alembic backfill migration.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

# The chain's genesis predecessor hash (64 hex zeros).
GENESIS_HASH = "0" * 64


@dataclass(frozen=True, slots=True)
class AuditFacts:
    """The immutable, hash-covered facts of a single audit entry."""

    sequence: int
    occurred_at: datetime
    action: str
    resource_type: str
    resource_id: str
    actor_type: str
    actor_user_id: UUID | None
    organization_id: UUID | None
    request_id: str | None
    correlation_id: str | None
    session_id: str | None
    ip_hash: str | None
    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None


def _canonical(facts: AuditFacts) -> str:
    payload: dict[str, Any] = {
        "sequence": facts.sequence,
        "occurred_at": facts.occurred_at.isoformat(),
        "action": facts.action,
        "resource_type": facts.resource_type,
        "resource_id": facts.resource_id,
        "actor_type": facts.actor_type,
        "actor_user_id": str(facts.actor_user_id) if facts.actor_user_id else None,
        "organization_id": str(facts.organization_id) if facts.organization_id else None,
        "request_id": facts.request_id,
        "correlation_id": facts.correlation_id,
        "session_id": facts.session_id,
        "ip_hash": facts.ip_hash,
        "before_state": facts.before_state,
        "after_state": facts.after_state,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def compute_entry_hash(prev_hash: str, facts: AuditFacts) -> str:
    """Return the SHA-256 hex digest linking ``facts`` to ``prev_hash``."""
    material = f"{prev_hash}\n{_canonical(facts)}".encode()
    return hashlib.sha256(material).hexdigest()


@dataclass(frozen=True, slots=True)
class ChainedEntry:
    facts: AuditFacts
    prev_hash: str | None
    entry_hash: str | None


def verify_chain(
    entries: Iterable[ChainedEntry], *, start_prev: str = GENESIS_HASH
) -> int | None:
    """Verify a contiguous, ascending run of entries.

    Returns the ``sequence`` of the first entry that fails verification (a
    broken link or a recomputed hash mismatch), or ``None`` if the whole run is
    intact.
    """
    expected_prev = start_prev
    for entry in entries:
        if entry.prev_hash != expected_prev:
            return entry.facts.sequence
        recomputed = compute_entry_hash(expected_prev, entry.facts)
        if recomputed != entry.entry_hash:
            return entry.facts.sequence
        expected_prev = recomputed
    return None
