"""Ordered acceptance — the monitoring.v1 sequence policy.

The contract: sequences are scoped to ``(source_id, source_instance)``, the first
message of an instance is sequence 1, and each subsequent message must be the
next one. A gap or an unknown older sequence is **refused with 409** and the last
accepted state is retained. The producer retries in order.

This replaces the previous receiver's policy, which accepted everything and
recorded gaps for visibility. That was a coherent design for a different
contract, and it is wrong for this one: a publisher built to retry until accepted
would have retried forever against a receiver that had already accepted.

What survives from it is the **observability**, deliberately separated from the
acceptance decision. A refusal is counted and recorded so operators can see
delivery trouble — without any refused message ever appearing as accepted data.
"""

from __future__ import annotations

from dataclasses import dataclass
import json

#: Bounded so a persistently misordered publisher cannot grow one row without
#: limit. These are diagnostics; losing the oldest is acceptable.
MAX_RECORDED_GAPS = 64


@dataclass(frozen=True, slots=True)
class SequenceDecision:
    """What the sequence policy says about one message."""

    #: "accept" | "refuse_gap" | "refuse_old"
    action: str
    expected: int | None
    received: int
    detail: str

    @property
    def accepted(self) -> bool:
        return self.action == "accept"


def decide(*, received: int, last_accepted: int | None) -> SequenceDecision:
    """Apply the contract's ordered-acceptance rule.

    ``last_accepted`` is None for an instance the receiver has never seen, in
    which case the contract expects sequence 1. Anything else from a fresh
    instance is a gap: the producer either lost its first messages or this is a
    silent resequence, and the contract requires resynchronisation to be an
    explicit operational step rather than something the receiver absorbs.

    Duplicates are **not** handled here. A redelivery is recognised by its
    content address before the sequence is consulted, so a previously accepted
    message can be acknowledged again even after later sequences — exactly as the
    contract requires.
    """
    if last_accepted is None:
        if received == 1:
            return SequenceDecision(
                action="accept", expected=1, received=received, detail="first message of instance"
            )
        return SequenceDecision(
            action="refuse_gap",
            expected=1,
            received=received,
            detail=(
                f"first message of a new source_instance must be sequence 1, got {received}; "
                "resynchronisation is an explicit operational step"
            ),
        )

    expected = last_accepted + 1
    if received == expected:
        return SequenceDecision(
            action="accept", expected=expected, received=received, detail="next expected sequence"
        )
    if received > expected:
        return SequenceDecision(
            action="refuse_gap",
            expected=expected,
            received=received,
            detail=f"expected sequence {expected}, got {received}",
        )
    return SequenceDecision(
        action="refuse_old",
        expected=expected,
        received=received,
        detail=(
            f"sequence {received} is older than the last accepted {last_accepted} "
            "and is not a known message"
        ),
    )


def record_gap(existing: str | None, decision: SequenceDecision, at: str) -> str:
    """Append a refusal to the bounded observability log.

    Recording a refusal is not accepting it. Nothing in the read path treats
    these entries as data — they exist so an operator can see that a publisher is
    delivering out of order, which is otherwise invisible until someone notices
    the sequence has stopped advancing.
    """
    entries = load_gaps(existing)
    entries.append(
        {
            "expected": decision.expected,
            "received": decision.received,
            "action": decision.action,
            "at": at,
        }
    )
    return json.dumps(entries[-MAX_RECORDED_GAPS:], separators=(",", ":"))


def load_gaps(raw: str | None) -> list[dict]:
    """Parse the recorded refusals, tolerating a corrupt value.

    A malformed diagnostics column must not take the ingest path down; losing
    diagnostics is far less bad than refusing telemetry because of them.
    """
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]
