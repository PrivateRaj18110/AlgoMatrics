"""Trades router."""

from fastapi import APIRouter, Query

from app.core.mock_policy import allow_mock_fixtures
from app.repositories import trades_repo
from app.schemas.trade import Trade
from app.services import algomatrics_service

router = APIRouter(tags=["trades"])


@router.get("", response_model=list[Trade], summary="List trades")
def list_trades(limit: int | None = Query(None, ge=1, le=1000)) -> list[dict]:
    """Return the telemetry blotter.

    Production never substitutes SaaS fills or mock fixtures for Google trades.
    """
    if not allow_mock_fixtures():
        rows = trades_repo.list()
        return rows[:limit] if limit else rows
    live = algomatrics_service.trades(limit)
    if live is not None:
        return live
    rows = trades_repo.list()
    return rows[:limit] if limit else rows
