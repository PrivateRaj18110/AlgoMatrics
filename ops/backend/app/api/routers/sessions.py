"""Read-only trading session APIs for the ops dashboard."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.session import SessionDetailView, SessionView
from app.services import session_service
from app.services.session_service import SessionNotFoundError

router = APIRouter(tags=["sessions"])


def _raise_for(exc: Exception) -> None:
    if isinstance(exc, SessionNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    raise exc


@router.get("", response_model=list[SessionView], summary="List trading sessions")
def list_sessions(
    limit: int = Query(100, ge=1, le=500),
    machine_id: str | None = Query(default=None, alias="machineId"),
    session_status: Literal["open", "closed"] | None = Query(default=None, alias="status"),
) -> list[dict]:
    return session_service.list_sessions(
        limit=limit,
        machine_id=machine_id,
        status=session_status,
    )


@router.get(
    "/{session_id}",
    response_model=SessionDetailView,
    summary="Get trading session detail",
)
def get_session_detail(
    session_id: str,
    machine_id: str | None = Query(default=None, alias="machineId"),
    event_limit: int = Query(100, ge=1, le=500, alias="eventLimit"),
) -> dict:
    try:
        return session_service.get_session_detail(
            session_id,
            machine_id=machine_id,
            event_limit=event_limit,
        )
    except Exception as exc:
        _raise_for(exc)
        raise
