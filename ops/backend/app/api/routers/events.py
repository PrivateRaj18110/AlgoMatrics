"""Events router."""

from fastapi import APIRouter, Query

from app.repositories import events_repo
from app.schemas.event import SystemEvent

router = APIRouter(tags=["events"])


@router.get("", response_model=list[SystemEvent], summary="List system events")
def list_events(limit: int = Query(200, ge=1, le=400)) -> list[dict]:
    """Return the system event feed, newest first."""
    return events_repo.list()[:limit]
