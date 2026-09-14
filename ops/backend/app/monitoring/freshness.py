"""Freshness under monitoring.v1 — read, never computed.

The previous receiver evaluated a validity horizon (``stale_after``) against the
clock. **monitoring.v1 has no horizon.** The producer asserts freshness as a
state, derived from source validity and trust, and the contract is explicit that
receiver freshness must use those and *not* arrival or publication time.

So this module reads. It does not subtract timestamps, does not consult the
clock, and cannot turn a value stale or fresh on its own. There is deliberately
no ``evaluate(now=...)`` function any more — its absence is the guarantee.

Two failure modes this prevents, both of which the previous model allowed:

* a value the source called STALE being shown as live because a message arrived
  recently
* a value the source called fresh being shown as stale because a local timer
  expired while the source was perfectly healthy

``freshness.source`` is the state. It is passed through to the screen unchanged,
including spellings this receiver does not recognise: the contract says an
unfamiliar value must not be reinterpreted as healthy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: States seen in the producer's own fixtures and contract text. The list is
#: *not* used to validate — an unfamiliar state is preserved as-is, never
#: rejected and never downgraded to UNKNOWN.
KNOWN_FRESHNESS_STATES = frozenset(
    {"UNKNOWN", "STALE", "LIVE", "FRESH", "INCOMPLETE", "UNTRUSTED", "SYNTHETIC_CLOCK"}
)


@dataclass(frozen=True, slots=True)
class Freshness:
    """The source's own freshness assertion, unmodified."""

    #: ``freshness.source`` verbatim. None only when the producer omitted it.
    source_state: str | None
    #: ``freshness.derived_at`` — when the *source* derived this, not when we got it.
    derived_at: str | None
    reason: str | None
    #: Everything else the producer sent, retained so a future field is not lost.
    extra: dict[str, Any]

    @property
    def is_recognised(self) -> bool:
        return self.source_state in KNOWN_FRESHNESS_STATES

    def as_dict(self) -> dict[str, Any]:
        """Serialise for the API, preserving unrecognised fields."""
        payload: dict[str, Any] = {
            "source": self.source_state,
            "derivedAt": self.derived_at,
            "reason": self.reason,
            # Flagged so the UI can show "the source said something we do not
            # recognise" rather than silently rendering it as normal.
            "recognisedByReceiver": self.is_recognised,
        }
        if self.extra:
            payload["additional"] = self.extra
        return payload


def read(freshness: Any) -> Freshness:
    """Read the producer's freshness object. Never computes anything."""
    if not isinstance(freshness, dict):
        return Freshness(source_state=None, derived_at=None, reason=None, extra={})
    known = {"source", "derived_at", "reason"}
    return Freshness(
        source_state=freshness.get("source"),
        derived_at=freshness.get("derived_at"),
        reason=freshness.get("reason"),
        extra={key: value for key, value in freshness.items() if key not in known},
    )


def read_trust(trust: Any) -> dict[str, Any]:
    """Pass the producer's trust object through untouched.

    Successful authentication, schema validation and persistence say nothing
    about whether the *data* is trustworthy. Nothing here upgrades a status.
    """
    return dict(trust) if isinstance(trust, dict) else {}


def read_coverage(coverage: Any) -> dict[str, Any]:
    """Pass the producer's coverage object through untouched.

    No ratio is computed from message arrival. If the producer says coverage is
    UNKNOWN or INCOMPLETE, that is what the dashboard shows — a message arriving
    is not evidence that the capture was complete.
    """
    return dict(coverage) if isinstance(coverage, dict) else {}
