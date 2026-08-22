"""Heartbeat-age status, matching ops-api (do not invent a new timeout)."""

from __future__ import annotations

from datetime import UTC, datetime

DEGRADED_AFTER_SEC = 30.0
OFFLINE_AFTER_SEC = 120.0


def _as_utc(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.replace("Z", "+00:00")
        try:
            value = datetime.fromisoformat(text)
        except ValueError:
            return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def derive_machine_status(
    stored_status: str | None,
    last_heartbeat: datetime | str | None,
    *,
    live: bool = True,
    now: datetime | None = None,
) -> str:
    if not live:
        return stored_status or "unknown"
    heartbeat = _as_utc(last_heartbeat)
    if heartbeat is None:
        return "unknown"
    current = now or datetime.now(UTC)
    age = max(0.0, (current - heartbeat).total_seconds())
    if age > OFFLINE_AFTER_SEC:
        return "offline"
    if age > DEGRADED_AFTER_SEC:
        return "degraded"
    return stored_status or "online"
