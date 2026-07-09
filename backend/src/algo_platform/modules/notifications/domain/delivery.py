"""Multi-channel notification routing rules.

Pure and framework-free so the delivery policy is unit testable and reusable by
the service, API, and the worker fan-out. Complements the existing in-app +
WebSocket notification path rather than replacing it: in-app is always written;
this module decides which *additional* channels (email, webhook) a given
notification should be delivered on for a specific recipient.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time
from enum import StrEnum


class Channel(StrEnum):
    """A delivery surface for a notification."""

    IN_APP = "in_app"
    EMAIL = "email"
    WEBHOOK = "webhook"


class Severity(StrEnum):
    """Notification severity, ordered least → most urgent."""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    CRITICAL = "critical"


# Explicit rank so severities can be compared without relying on enum order.
_SEVERITY_RANK: dict[Severity, int] = {
    Severity.INFO: 0,
    Severity.SUCCESS: 1,
    Severity.WARNING: 2,
    Severity.CRITICAL: 3,
}


def severity_rank(severity: str) -> int:
    """Rank of a severity string; unknown values sort as ``info`` (0)."""

    try:
        return _SEVERITY_RANK[Severity(severity)]
    except ValueError:
        return 0


@dataclass(frozen=True, slots=True)
class QuietHours:
    """A daily do-not-disturb window in the recipient's own local time.

    ``start`` == ``end`` means the window is empty (never quiet). A window that
    wraps past midnight (``start`` > ``end``) is supported.
    """

    start: time
    end: time

    def contains(self, moment: time) -> bool:
        if self.start == self.end:
            return False
        if self.start < self.end:
            return self.start <= moment < self.end
        # Wraps past midnight, e.g. 22:00 → 07:00.
        return moment >= self.start or moment < self.end


@dataclass(frozen=True, slots=True)
class DeliveryPreference:
    """A recipient's multi-channel delivery policy.

    Defaults preserve the historical behaviour: in-app only, every severity,
    no quiet hours. Email/webhook are strictly opt-in.
    """

    enabled_channels: frozenset[Channel] = field(
        default_factory=lambda: frozenset({Channel.IN_APP})
    )
    # Notification ``type`` values the recipient has muted entirely.
    muted_types: frozenset[str] = frozenset()
    # Minimum severity that may leave the in-app surface (email/webhook).
    min_severity: Severity = Severity.INFO
    quiet_hours: QuietHours | None = None
    # Critical notifications bypass quiet hours when True.
    critical_overrides_quiet: bool = True

    def is_muted(self, type_: str) -> bool:
        return type_ in self.muted_types


def resolve_channels(
    preference: DeliveryPreference,
    *,
    type_: str,
    severity: str,
    local_time: time | None = None,
) -> frozenset[Channel]:
    """Channels a notification should be delivered on for one recipient.

    In-app is always included (the record is written regardless) unless the
    type is muted. Email/webhook are included only when enabled, at or above
    ``min_severity``, and outside quiet hours — except that a critical
    notification bypasses quiet hours when ``critical_overrides_quiet``.
    """

    if preference.is_muted(type_):
        return frozenset()

    # In-app is implicit even if not explicitly enabled: the recipient can
    # always see it in the bell. Email/webhook are the opt-in surfaces.
    channels = {Channel.IN_APP}

    is_critical = Severity(severity) is Severity.CRITICAL if _is_severity(severity) else False
    if severity_rank(severity) < severity_rank(preference.min_severity):
        return frozenset(channels)

    if preference.quiet_hours is not None and local_time is not None:
        quiet = preference.quiet_hours.contains(local_time)
        if quiet and not (is_critical and preference.critical_overrides_quiet):
            return frozenset(channels)

    for external in (Channel.EMAIL, Channel.WEBHOOK):
        if external in preference.enabled_channels:
            channels.add(external)
    return frozenset(channels)


def _is_severity(value: str) -> bool:
    try:
        Severity(value)
    except ValueError:
        return False
    return True
