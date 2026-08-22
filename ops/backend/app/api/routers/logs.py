"""Logs router."""

from fastapi import APIRouter, Query

from app.repositories import logs_repo
from app.schemas.log import LogEntry, LogSource

router = APIRouter(tags=["logs"])


@router.get("", response_model=list[LogEntry], summary="List log lines")
def list_logs(
    source: LogSource | None = Query(None, description="Filter to a single stream."),
    limit: int = Query(500, ge=1, le=1000),
) -> list[dict]:
    """Return log lines, optionally filtered to one stream, newest first."""
    return logs_repo.by_source(source)[:limit]
