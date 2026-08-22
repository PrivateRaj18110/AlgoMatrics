"""Read-only trading-session dashboard service."""

from __future__ import annotations

from typing import Any

from app.repositories import eod_repo, events_repo, sessions_repo


class SessionNotFoundError(LookupError):
    """Requested trading session does not exist."""


def list_sessions(
    *,
    limit: int = 100,
    machine_id: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    return sessions_repo.list(limit=limit, machine_id=machine_id, status=status)


def get_session_detail(
    session_id: str,
    *,
    machine_id: str | None = None,
    event_limit: int = 100,
) -> dict[str, Any]:
    session = sessions_repo.get(session_id, machine_id=machine_id)
    if session is None:
        raise SessionNotFoundError("session not found")
    events = events_repo.query(
        limit=event_limit,
        machine_id=machine_id or session.get("machineId"),
        session_id=session_id,
    )
    datasets = [
        dataset
        for dataset in eod_repo.list(limit=500, machine_id=machine_id or session.get("machineId"))
        if dataset.get("sessionId") == session_id
    ][:25]
    return {
        "session": session,
        "recentEvents": events,
        "eodDatasets": datasets,
    }
