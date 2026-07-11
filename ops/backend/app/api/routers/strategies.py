"""Strategies router."""

from fastapi import APIRouter, HTTPException

from app.repositories import strategies_repo
from app.schemas.strategy import Strategy
from app.services import algomatrics_service

router = APIRouter(tags=["strategies"])


@router.get("", response_model=list[Strategy], summary="List strategies")
def list_strategies() -> list[dict]:
    live = algomatrics_service.strategies()
    return live if live is not None else strategies_repo.list()


@router.get("/{strategy_id}", response_model=Strategy, summary="Get a strategy")
def get_strategy(strategy_id: str) -> dict:
    if algomatrics_service.strategies() is not None:
        strategy = algomatrics_service.strategy(strategy_id)
    else:
        strategy = strategies_repo.get(strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy
