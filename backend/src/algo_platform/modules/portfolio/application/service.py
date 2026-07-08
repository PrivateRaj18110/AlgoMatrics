"""Portfolio read models: dashboard summary, equity curve, analytics."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.brokerage.infrastructure.models import TradingAccountModel
from algo_platform.modules.instruments.application.directory import InstrumentDirectory
from algo_platform.modules.portfolio.infrastructure.models import PortfolioSnapshotModel
from algo_platform.modules.trading.infrastructure.models import (
    ExecutionModel,
    OrderModel,
    PositionModel,
)
from algo_platform.shared.domain.types import TenantId, utc_now


@dataclass(frozen=True, slots=True)
class EquityPointDTO:
    as_of: datetime
    equity: Decimal
    cash: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    exposure: Decimal


@dataclass(frozen=True, slots=True)
class DailyPnlDTO:
    day: str
    realized_pnl: Decimal
    trades: int
    fees: Decimal


@dataclass(frozen=True, slots=True)
class MonthlyPnlDTO:
    month: str
    realized_pnl: Decimal
    trades: int


@dataclass(frozen=True, slots=True)
class PerformanceSummaryDTO:
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


@dataclass(frozen=True, slots=True)
class DashboardSummaryDTO:
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


class PortfolioQueryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- dashboard -------------------------------------------------------------

    async def dashboard_summary(
        self, organization_id: TenantId, *, active_strategies: int
    ) -> DashboardSummaryDTO:
        accounts = (
            (
                await self._session.execute(
                    select(TradingAccountModel).where(
                        TradingAccountModel.organization_id == organization_id,
                        TradingAccountModel.status == "active",
                    )
                )
            )
            .scalars()
            .all()
        )
        total_equity = sum((a.equity for a in accounts), Decimal("0"))
        total_cash = sum((a.cash_balance for a in accounts), Decimal("0"))
        starting = sum((a.starting_balance for a in accounts), Decimal("0"))

        positions = (
            (
                await self._session.execute(
                    select(PositionModel).where(
                        PositionModel.organization_id == organization_id,
                        PositionModel.quantity != 0,
                    )
                )
            )
            .scalars()
            .all()
        )
        unrealized = Decimal("0")
        for p in positions:
            mark = p.last_mark if p.last_mark is not None else p.average_price
            unrealized += (mark - p.average_price) * p.quantity

        open_orders = int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(OrderModel)
                    .where(
                        OrderModel.organization_id == organization_id,
                        OrderModel.status.in_(
                            [
                                "pending_risk",
                                "approved",
                                "submitted",
                                "partially_filled",
                                "cancel_pending",
                            ]
                        ),
                    )
                )
            ).scalar_one()
        )

        day_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_row = (
            await self._session.execute(
                select(
                    func.coalesce(func.sum(ExecutionModel.realized_delta), 0),
                    func.count(),
                ).where(
                    ExecutionModel.organization_id == organization_id,
                    ExecutionModel.executed_at >= day_start,
                )
            )
        ).one()
        realized_today = Decimal(str(today_row[0]))
        trades_today = int(today_row[1])

        return DashboardSummaryDTO(
            total_equity=total_equity,
            total_cash=total_cash,
            starting_balance=starting,
            realized_pnl_today=realized_today,
            unrealized_pnl=unrealized,
            open_positions=len(positions),
            open_orders=open_orders,
            active_strategies=active_strategies,
            accounts=len(accounts),
            trades_today=trades_today,
        )

    # -- equity curve --------------------------------------------------------------

    async def equity_curve(
        self,
        organization_id: TenantId,
        *,
        account_id: UUID | None,
        days: int,
        max_points: int = 500,
    ) -> list[EquityPointDTO]:
        since = utc_now() - timedelta(days=days)
        stmt = (
            select(PortfolioSnapshotModel)
            .where(
                PortfolioSnapshotModel.organization_id == organization_id,
                PortfolioSnapshotModel.as_of >= since,
            )
            .order_by(PortfolioSnapshotModel.as_of)
        )
        if account_id is not None:
            stmt = stmt.where(PortfolioSnapshotModel.account_id == account_id)
        rows = (await self._session.execute(stmt)).scalars().all()

        if account_id is None and rows:
            # Aggregate multi-account snapshots into aligned time buckets.
            buckets: dict[str, dict[str, Decimal]] = {}
            order: list[str] = []
            for r in rows:
                key = r.as_of.strftime("%Y-%m-%dT%H:%M")
                if key not in buckets:
                    buckets[key] = {
                        "equity": Decimal("0"),
                        "cash": Decimal("0"),
                        "realized": Decimal("0"),
                        "unrealized": Decimal("0"),
                        "exposure": Decimal("0"),
                    }
                    order.append(key)
                bucket = buckets[key]
                bucket["equity"] += r.equity
                bucket["cash"] += r.cash
                bucket["realized"] += r.realized_pnl
                bucket["unrealized"] += r.unrealized_pnl
                bucket["exposure"] += r.exposure
            points = [
                EquityPointDTO(
                    as_of=datetime.fromisoformat(key + ":00+00:00"),
                    equity=buckets[key]["equity"],
                    cash=buckets[key]["cash"],
                    realized_pnl=buckets[key]["realized"],
                    unrealized_pnl=buckets[key]["unrealized"],
                    exposure=buckets[key]["exposure"],
                )
                for key in order
            ]
        else:
            points = [
                EquityPointDTO(
                    as_of=r.as_of,
                    equity=r.equity,
                    cash=r.cash,
                    realized_pnl=r.realized_pnl,
                    unrealized_pnl=r.unrealized_pnl,
                    exposure=r.exposure,
                )
                for r in rows
            ]
        if len(points) > max_points:
            step = math.ceil(len(points) / max_points)
            points = [*points[::step], points[-1]]
        return points

    # -- pnl series ------------------------------------------------------------------

    async def daily_pnl(
        self, organization_id: TenantId, *, days: int, account_id: UUID | None = None
    ) -> list[DailyPnlDTO]:
        since = utc_now() - timedelta(days=days)
        day_col = cast(ExecutionModel.executed_at, Date)
        stmt = (
            select(
                day_col.label("day"),
                func.coalesce(func.sum(ExecutionModel.realized_delta), 0),
                func.count(),
                func.coalesce(func.sum(ExecutionModel.fee), 0),
            )
            .where(
                ExecutionModel.organization_id == organization_id,
                ExecutionModel.executed_at >= since,
            )
            .group_by(day_col)
            .order_by(day_col)
        )
        if account_id is not None:
            stmt = stmt.where(ExecutionModel.account_id == account_id)
        rows = (await self._session.execute(stmt)).all()
        return [
            DailyPnlDTO(
                day=str(row[0]),
                realized_pnl=Decimal(str(row[1])),
                trades=int(row[2]),
                fees=Decimal(str(row[3])),
            )
            for row in rows
        ]

    async def monthly_pnl(self, organization_id: TenantId, *, months: int) -> list[MonthlyPnlDTO]:
        since = utc_now() - timedelta(days=31 * months)
        month_col = func.to_char(ExecutionModel.executed_at, "YYYY-MM")
        stmt = (
            select(
                month_col.label("month"),
                func.coalesce(func.sum(ExecutionModel.realized_delta), 0),
                func.count(),
            )
            .where(
                ExecutionModel.organization_id == organization_id,
                ExecutionModel.executed_at >= since,
            )
            .group_by(month_col)
            .order_by(month_col)
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            MonthlyPnlDTO(
                month=str(row[0]),
                realized_pnl=Decimal(str(row[1])),
                trades=int(row[2]),
            )
            for row in rows
        ]

    # -- performance summary -----------------------------------------------------------

    async def performance_summary(
        self, organization_id: TenantId, *, days: int = 90
    ) -> PerformanceSummaryDTO:
        since = utc_now() - timedelta(days=days)
        executions = (
            (
                await self._session.execute(
                    select(
                        ExecutionModel.realized_delta,
                        ExecutionModel.fee,
                    ).where(
                        ExecutionModel.organization_id == organization_id,
                        ExecutionModel.executed_at >= since,
                    )
                )
            )
            .tuples()
            .all()
        )
        total_trades = len(executions)
        total_fees = sum((Decimal(str(f)) for _, f in executions), Decimal("0"))
        closing = [Decimal(str(d)) for d, _ in executions if Decimal(str(d)) != 0]
        wins = [d for d in closing if d > 0]
        losses = [d for d in closing if d < 0]
        win_rate = Decimal(len(wins)) / Decimal(len(closing)) * 100 if closing else Decimal("0")
        gross_profit = sum(wins, Decimal("0"))
        gross_loss = -sum(losses, Decimal("0"))
        profit_factor = (
            (gross_profit / gross_loss).quantize(Decimal("0.01")) if gross_loss > 0 else None
        )
        average_win = (gross_profit / len(wins)).quantize(Decimal("0.01")) if wins else Decimal("0")
        average_loss = (
            (gross_loss / len(losses)).quantize(Decimal("0.01")) if losses else Decimal("0")
        )
        total_realized = sum(closing, Decimal("0"))

        positions = (
            (
                await self._session.execute(
                    select(PositionModel).where(
                        PositionModel.organization_id == organization_id,
                        PositionModel.quantity != 0,
                    )
                )
            )
            .scalars()
            .all()
        )
        unrealized = Decimal("0")
        exposure = Decimal("0")
        for p in positions:
            mark = p.last_mark if p.last_mark is not None else p.average_price
            unrealized += (mark - p.average_price) * p.quantity
            exposure += abs(p.quantity) * mark

        curve = await self.equity_curve(organization_id, account_id=None, days=days)
        max_drawdown = Decimal("0")
        peak: Decimal | None = None
        for point in curve:
            if peak is None or point.equity > peak:
                peak = point.equity
            if peak and peak > 0:
                drawdown = (peak - point.equity) / peak * 100
                max_drawdown = max(max_drawdown, drawdown)

        daily = await self.daily_pnl(organization_id, days=min(days, 90))
        returns = [float(d.realized_pnl) for d in daily]
        volatility = Decimal("0")
        if len(returns) >= 2:
            mean = sum(returns) / len(returns)
            variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
            base_equity = float(curve[0].equity) if curve and curve[0].equity else 0.0
            if base_equity > 0:
                volatility = Decimal(str(round(math.sqrt(variance) / base_equity * 100, 4)))

        return PerformanceSummaryDTO(
            total_realized_pnl=total_realized,
            total_unrealized_pnl=unrealized,
            total_fees=total_fees,
            total_trades=total_trades,
            closing_trades=len(closing),
            win_rate_pct=win_rate.quantize(Decimal("0.01")),
            profit_factor=profit_factor,
            average_win=average_win,
            average_loss=average_loss,
            max_drawdown_pct=max_drawdown.quantize(Decimal("0.01")),
            daily_return_volatility_pct=volatility,
            gross_exposure=exposure,
        )

    async def exposure_breakdown(self, organization_id: TenantId) -> list[dict[str, Any]]:
        positions = (
            (
                await self._session.execute(
                    select(PositionModel).where(
                        PositionModel.organization_id == organization_id,
                        PositionModel.quantity != 0,
                    )
                )
            )
            .scalars()
            .all()
        )
        instruments = await InstrumentDirectory(self._session).get_map(
            [position.instrument_id for position in positions]
        )
        breakdown: list[dict[str, Any]] = []
        for p in positions:
            instrument = instruments.get(p.instrument_id)
            if instrument is None:
                continue
            mark = p.last_mark if p.last_mark is not None else p.average_price
            breakdown.append(
                {
                    "instrument_id": str(p.instrument_id),
                    "symbol": instrument.symbol,
                    "asset_class": instrument.asset_class,
                    "currency": instrument.currency,
                    "quantity": str(p.quantity),
                    "market_value": str(abs(p.quantity) * mark),
                    "side": "long" if p.quantity > 0 else "short",
                }
            )
        return breakdown
