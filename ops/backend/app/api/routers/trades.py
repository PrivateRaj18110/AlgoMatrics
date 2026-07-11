"""Trades router."""

from fastapi import APIRouter, Query

from app.repositories import trades_repo
from app.schemas.trade import Trade
from app.services import algomatrics_service

router = APIRouter(tags=["trades"])


@router.get("", response_model=list[Trade], summary="List trades")
def list_trades(limit: int | None = Query(None, ge=1, le=1000)) -> list[dict]:
    """Return the trade blotter, optionally capped to the most recent ``limit``."""
    live = algomatrics_service.trades(limit)
    if live is not None:
        return live
    rows = trades_repo.list()
    return rows[:limit] if limit else rows
