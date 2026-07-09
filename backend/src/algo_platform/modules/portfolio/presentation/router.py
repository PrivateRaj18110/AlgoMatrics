from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict

from algo_platform.api.dependencies.core import SessionDep
from algo_platform.api.dependencies.tenant import TenantContext, require_permission
from algo_platform.modules.organizations.domain.roles import Permission
from algo_platform.modules.portfolio.application.service import PortfolioQueryService
from algo_platform.modules.strategies.application.service import count_active_runs_for

router = APIRouter(tags=["dashboard"])

AnalyticsTenant = Annotated[TenantContext, Depends(require_permission(Permission.ANALYTICS_VIEW))]


def get_portfolio_queries(session: SessionDep) -> PortfolioQueryService:
    return PortfolioQueryService(session)


PortfolioDep = Annotated[PortfolioQueryService, Depends(get_portfolio_queries)]


class DashboardSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_equity: Decimal
    total_cash: Decimal
    starting_balance: Decimal
    realized_pnl_today: Decimal
    unrealized_pnl: Decimal
    open_positions: int
    open_orders: int
    active_strategies: int
    accounts: int
    trades_today: int


class EquityPointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    as_of: datetime
    equity: Decimal
    cash: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    exposure: Decimal


class DailyPnlResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    day: str
    realized_pnl: Decimal
    trades: int
    fees: Decimal


class MonthlyPnlResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    month: str
    realized_pnl: Decimal
    trades: int


class PerformanceSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_realized_pnl: Decimal
    total_unrealized_pnl: Decimal
    total_fees: Decimal
    total_trades: int
    closing_trades: int
    win_rate_pct: Decimal
    profit_factor: Decimal | None
    average_win: Decimal
    average_loss: Decimal
    max_drawdown_pct: Decimal
    daily_return_volatility_pct: Decimal
    gross_exposure: Decimal
    sharpe_ratio: Decimal
    sortino_ratio: Decimal
    calmar_ratio: Decimal
    annualized_return_pct: Decimal


@router.get("/dashboard/summary", response_model=DashboardSummaryResponse)
async def dashboard_summary(
    tenant: AnalyticsTenant,
    portfolio: PortfolioDep,
    session: SessionDep,
) -> DashboardSummaryResponse:
    active = await count_active_runs_for(session, tenant.organization_id)
    summary = await portfolio.dashboard_summary(tenant.organization_id, active_strategies=active)
    return DashboardSummaryResponse.model_validate(summary)


@router.get("/portfolio/equity-curve", response_model=list[EquityPointResponse])
async def equity_curve(
    tenant: AnalyticsTenant,
    portfolio: PortfolioDep,
    account_id: Annotated[UUID | None, Query()] = None,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
) -> list[EquityPointResponse]:
    points = await portfolio.equity_curve(tenant.organization_id, account_id=account_id, days=days)
    return [EquityPointResponse.model_validate(p) for p in points]


@router.get("/analytics/daily-pnl", response_model=list[DailyPnlResponse])
async def daily_pnl(
    tenant: AnalyticsTenant,
    portfolio: PortfolioDep,
    days: Annotated[int, Query(ge=1, le=365)] = 90,
    account_id: Annotated[UUID | None, Query()] = None,
) -> list[DailyPnlResponse]:
    series = await portfolio.daily_pnl(tenant.organization_id, days=days, account_id=account_id)
    return [DailyPnlResponse.model_validate(d) for d in series]


@router.get("/analytics/monthly-pnl", response_model=list[MonthlyPnlResponse])
async def monthly_pnl(
    tenant: AnalyticsTenant,
    portfolio: PortfolioDep,
    months: Annotated[int, Query(ge=1, le=24)] = 12,
) -> list[MonthlyPnlResponse]:
    series = await portfolio.monthly_pnl(tenant.organization_id, months=months)
    return [MonthlyPnlResponse.model_validate(m) for m in series]


@router.get("/analytics/summary", response_model=PerformanceSummaryResponse)
async def performance_summary(
    tenant: AnalyticsTenant,
    portfolio: PortfolioDep,
    days: Annotated[int, Query(ge=7, le=365)] = 90,
) -> PerformanceSummaryResponse:
    summary = await portfolio.performance_summary(tenant.organization_id, days=days)
    return PerformanceSummaryResponse.model_validate(summary)


@router.get("/analytics/exposure", response_model=list[dict[str, Any]])
async def exposure(tenant: AnalyticsTenant, portfolio: PortfolioDep) -> list[dict[str, Any]]:
    return await portfolio.exposure_breakdown(tenant.organization_id)
