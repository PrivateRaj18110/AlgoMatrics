"""Backtesting HTTP API."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from algo_platform.api.dependencies.core import SessionDep
from algo_platform.api.dependencies.pagination import PageDep
from algo_platform.api.dependencies.tenant import TenantContext, require_permission
from algo_platform.modules.organizations.domain.roles import Permission
from algo_platform.modules.strategies.application.backtest_service import BacktestService
from algo_platform.modules.strategies.application.backtest_signals import available_signal_types
from algo_platform.modules.strategies.domain.backtest import BacktestConfig

router = APIRouter(prefix="/backtests", tags=["backtesting"])

ViewDep = Annotated[TenantContext, Depends(require_permission(Permission.STRATEGIES_VIEW))]
ManageDep = Annotated[TenantContext, Depends(require_permission(Permission.STRATEGIES_MANAGE))]


class BarInput(BaseModel):
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


class ConfigInput(BaseModel):
    initial_cash: float = Field(default=100_000.0, gt=0)
    fee_bps: float = Field(default=2.0, ge=0, le=1000)
    slippage_bps: float = Field(default=1.0, ge=0, le=1000)
    periods_per_year: int = Field(default=252, ge=1, le=100_000)

    def to_config(self) -> BacktestConfig:
        return BacktestConfig(**self.model_dump())


class RunBacktestRequest(BaseModel):
    signal_type: str
    params: dict[str, float] = Field(default_factory=dict)
    bars: list[BarInput] = Field(min_length=2, max_length=20_000)
    config: ConfigInput = Field(default_factory=ConfigInput)


class MonteCarloRequest(RunBacktestRequest):
    iterations: int = Field(default=1000, ge=10, le=50_000)
    seed: int = 0


class OptimizeRequest(BaseModel):
    signal_type: str
    grid: dict[str, list[float]]
    bars: list[BarInput] = Field(min_length=2, max_length=20_000)
    objective: str = "sharpe"
    config: ConfigInput = Field(default_factory=ConfigInput)


def _bars(items: list[BarInput]) -> list[dict[str, float]]:
    return [b.model_dump() for b in items]


@router.get("/signal-types", response_model=list[str])
async def signal_types(tenant: ViewDep) -> list[str]:
    return available_signal_types()


@router.post("/run", response_model=dict[str, Any], status_code=201)
async def run_backtest_endpoint(
    payload: RunBacktestRequest, tenant: ManageDep, session: SessionDep
) -> dict[str, Any]:
    run_id, result = await BacktestService(session).run(
        tenant.organization_id,
        signal_type=payload.signal_type,
        params=payload.params,
        bars=_bars(payload.bars),
        config=payload.config.to_config(),
    )
    return {
        "id": str(run_id),
        "total_return_pct": result.total_return_pct,
        "max_drawdown_pct": result.max_drawdown_pct,
        "sharpe": result.sharpe,
        "sortino": result.sortino,
        "calmar": result.calmar,
        "annualized_return_pct": result.annualized_return_pct,
        "trades": result.trades,
        "win_rate_pct": result.win_rate_pct,
        "ending_equity": result.ending_equity,
    }


@router.post("/monte-carlo", response_model=dict[str, Any])
async def monte_carlo_endpoint(
    payload: MonteCarloRequest, tenant: ManageDep, session: SessionDep
) -> dict[str, Any]:
    service = BacktestService(session)
    _run_id, result = await service.run(
        tenant.organization_id,
        signal_type=payload.signal_type,
        params=payload.params,
        bars=_bars(payload.bars),
        config=payload.config.to_config(),
    )
    mc = service.monte_carlo(result, iterations=payload.iterations, seed=payload.seed)
    return {
        "iterations": mc.iterations,
        "p5_return_pct": mc.p5_return_pct,
        "p50_return_pct": mc.p50_return_pct,
        "p95_return_pct": mc.p95_return_pct,
        "worst_drawdown_pct": mc.worst_drawdown_pct,
    }


@router.post("/optimize", response_model=list[dict[str, Any]])
async def optimize_endpoint(
    payload: OptimizeRequest, tenant: ManageDep, session: SessionDep
) -> list[dict[str, Any]]:
    return BacktestService(session).optimize(
        signal_type=payload.signal_type,
        grid=payload.grid,
        bars=_bars(payload.bars),
        objective=payload.objective,
        config=payload.config.to_config(),
    )


@router.get("", response_model=list[dict[str, Any]])
async def list_backtests(
    tenant: ViewDep, session: SessionDep, page: PageDep
) -> list[dict[str, Any]]:
    return await BacktestService(session).list_runs(
        tenant.organization_id, limit=page.limit, offset=page.offset
    )


@router.get("/{run_id}", response_model=dict[str, Any])
async def get_backtest(run_id: UUID, tenant: ViewDep, session: SessionDep) -> dict[str, Any]:
    return await BacktestService(session).get_run(tenant.organization_id, run_id)
