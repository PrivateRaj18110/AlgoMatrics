"""Events router."""

from datetime import datetime, timezone

from fastapi import APIRouter, Query

from app.repositories import events_repo
from app.schemas.common import Severity
from app.schemas.event import EventCategory, SystemEvent

router = APIRouter(tags=["events"])


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


@router.get("", response_model=list[SystemEvent], summary="List system events")
def list_events(
    limit: int = Query(200, ge=1, le=400),
    machine_id: str | None = Query(default=None, alias="machineId"),
    session_id: str | None = Query(default=None, alias="sessionId"),
    event_type: str | None = Query(default=None, alias="eventType"),
    strategy: str | None = None,
    symbol: str | None = None,
    severity: Severity | None = None,
    category: EventCategory | None = None,
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    """Return the bounded, filterable event timeline, newest first."""
    query = getattr(events_repo, "query", None)
    rows = (
        query(
            limit=limit,
            machine_id=machine_id,
            session_id=session_id,
            event_type=event_type,
            strategy=strategy,
            symbol=symbol,
            severity=severity,
            since=_parse_time(since),
            until=_parse_time(until),
        )
        if callable(query)
        else events_repo.list()[:limit]
    )
    if category:
        rows = [row for row in rows if row.get("category") == category]
    return rows[:limit]
