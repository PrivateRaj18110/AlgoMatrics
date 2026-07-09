"""Pure aggregation of dependency probe results into an overall readiness verdict.

Kept separate from the HTTP route so the roll-up rule (and the critical-vs-
optional distinction) is unit testable.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProbeResult:
    name: str
    healthy: bool
    critical: bool = True
    detail: str | None = None


def overall_status(results: list[ProbeResult]) -> str:
    """``"ok"`` when every *critical* probe is healthy, else ``"degraded"``.

    A failing non-critical probe is surfaced in the report but does not, on its
    own, take the service out of rotation.
    """

    return "ok" if all(r.healthy for r in results if r.critical) else "degraded"


def is_ready(results: list[ProbeResult]) -> bool:
    return overall_status(results) == "ok"
