"""Qualified values — the shape that stops UNKNOWN becoming zero.

Every monitored value in monitoring.v1 arrives as::

    {"state": "KNOWN", "value": 42}
    {"state": "UNKNOWN", "reason": "incident engine restarting"}
    {"state": "STALE", "value": 42, "as_of": "2026-09-11T09:12:00Z"}

The receiver's job is to move these from the wire to the screen **untouched**.
This module exists so that intent is enforceable rather than merely intended:
nothing in the receiver constructs a bare scalar from a qualified value, and
:func:`assert_preserves_states` gives the test suite a way to prove a payload
survived a round trip with every state intact.

There is deliberately no ``value_or_default``, no ``coalesce`` and no
``as_number`` helper here. Those are the functions that turn a dead feed into a
healthy-looking dashboard, and their absence is the point.
"""

from __future__ import annotations

from typing import Any, Final

KNOWN: Final = "KNOWN"
UNKNOWN: Final = "UNKNOWN"
STALE: Final = "STALE"
UNTRUSTED: Final = "UNTRUSTED"
INCOMPLETE: Final = "INCOMPLETE"
UNSUPPORTED: Final = "UNSUPPORTED"
NOT_APPLICABLE: Final = "NOT_APPLICABLE"
SIMULATED: Final = "SIMULATED"
SYNTHETIC_CLOCK: Final = "SYNTHETIC_CLOCK"

#: Every knowledge state in the contract.
KNOWLEDGE_STATES: Final = frozenset(
    {
        KNOWN,
        UNKNOWN,
        STALE,
        UNTRUSTED,
        INCOMPLETE,
        UNSUPPORTED,
        NOT_APPLICABLE,
        SIMULATED,
        SYNTHETIC_CLOCK,
    }
)

#: States that carry a value. The rest carry meaning precisely by not carrying one.
STATES_WITH_VALUE: Final = frozenset({KNOWN, STALE, UNTRUSTED, SIMULATED, SYNTHETIC_CLOCK})

#: States for which a value must never be materialised downstream.
STATES_WITHOUT_VALUE: Final = frozenset({UNKNOWN, UNSUPPORTED, NOT_APPLICABLE})


def is_qualified(value: Any) -> bool:
    """True when ``value`` is a qualified value rather than a bare scalar."""
    return (
        isinstance(value, dict)
        and isinstance(value.get("state"), str)
        and value["state"] in KNOWLEDGE_STATES
    )


def state_of(value: Any) -> str | None:
    """The knowledge state of ``value``, or None if it is not a qualified value."""
    return value["state"] if is_qualified(value) else None


def unknown(reason: str) -> dict[str, str]:
    """Build an UNKNOWN the *receiver itself* is asserting.

    Used where algomatric.in genuinely cannot answer — for example a freshness
    verdict with no publisher-supplied horizon. Never used to paper over a value
    the publisher did send.
    """
    return {"state": UNKNOWN, "reason": reason}


def walk_qualified(node: Any, path: str = "") -> list[tuple[str, str]]:
    """Every qualified value in a document, as ``(path, state)`` pairs.

    Used by tests and by the API serialisation check to prove that a payload
    still carries the states it arrived with.
    """
    found: list[tuple[str, str]] = []
    if is_qualified(node):
        found.append((path or "$", node["state"]))
        # A qualified value's `value` may itself be a structure; keep descending.
        if "value" in node:
            found.extend(walk_qualified(node["value"], f"{path}.value"))
        return found
    if isinstance(node, dict):
        for key in sorted(node):
            found.extend(walk_qualified(node[key], f"{path}.{key}" if path else key))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found.extend(walk_qualified(item, f"{path}[{index}]"))
    return found


def state_census(node: Any) -> dict[str, int]:
    """Count of each knowledge state appearing in a document."""
    census: dict[str, int] = {}
    for _, state in walk_qualified(node):
        census[state] = census.get(state, 0) + 1
    return census


def assert_preserves_states(original: Any, serialised: Any) -> None:
    """Raise unless ``serialised`` carries exactly the states of ``original``.

    The single assertion that matters for this whole system: a value that
    entered as UNKNOWN must not leave as anything else. Used in tests and
    available to any future transformation step that needs to prove itself.
    """
    before = walk_qualified(original)
    after = walk_qualified(serialised)
    if before != after:
        lost = sorted(set(before) - set(after))
        gained = sorted(set(after) - set(before))
        raise AssertionError(
            "qualified states were not preserved through serialisation.\n"
            f"  lost:   {lost}\n"
            f"  gained: {gained}"
        )
