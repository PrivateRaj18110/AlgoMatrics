"""Strategies router."""

from fastapi import APIRouter, HTTPException

from app.core.mock_policy import allow_mock_fixtures
from app.repositories import strategies_repo
from app.schemas.strategy import Strategy
from app.services import algomatrics_service
from app.services.telemetry_read_models import telemetry_strategies

router = APIRouter(tags=["strategies"])


@router.get("", response_model=list[Strategy], summary="List strategies")
def list_strategies() -> list[dict]:
    if not allow_mock_fixtures():
        return telemetry_strategies()
    live = algomatrics_service.strategies()
    return live if live is not None else strategies_repo.list()


@router.get("/{strategy_id}", response_model=Strategy, summary="Get a strategy")
def get_strategy(strategy_id: str) -> dict:
    if not allow_mock_fixtures():
        strategy = next((row for row in telemetry_strategies() if row["id"] == strategy_id), None)
    elif algomatrics_service.strategies() is not None:
        strategy = algomatrics_service.strategy(strategy_id)
    else:
        strategy = strategies_repo.get(strategy_id)
    if strategy is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return strategy
