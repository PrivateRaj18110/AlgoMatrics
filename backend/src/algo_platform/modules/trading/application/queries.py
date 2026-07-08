"""Read-side queries for orders, trades, and positions (CQRS-lite)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.api.dependencies.pagination import TimeCursor
from algo_platform.modules.instruments.application.directory import InstrumentDirectory
from algo_platform.modules.trading.infrastructure.models import (
    ExecutionModel,
    OrderModel,
    PositionModel,
)
from algo_platform.shared.domain.types import TenantId


@dataclass(frozen=True, slots=True)
class OrderListItemDTO:
    id: UUID
    account_id: UUID
    instrument_id: UUID
    symbol: str
    side: str
    order_type: str
    time_in_force: str
    quantity: Decimal
    limit_price: Decimal | None
    stop_price: Decimal | None
    status: str
    filled_quantity: Decimal
    average_fill_price: Decimal | None
    rejection_reason: str | None
    source: str
    client_order_id: str
    strategy_run_id: UUID | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class TradeListItemDTO:
    id: UUID
    order_id: UUID
    account_id: UUID
    instrument_id: UUID
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal
    fee: Decimal
    fee_currency: str
    executed_at: datetime


@dataclass(frozen=True, slots=True)
class PositionListItemDTO:
    id: UUID
    account_id: UUID
    instrument_id: UUID
    symbol: str
    side: str
    quantity: Decimal
    average_price: Decimal
    last_mark: Decimal | None
    market_value: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    fees_paid: Decimal
    updated_at: datetime


class TradingQueries:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._instruments = InstrumentDirectory(session)

    async def list_orders(
        self,
        organization_id: TenantId,
        *,
        account_id: UUID | None,
        status: str | None,
        instrument_id: UUID | None,
        cursor: TimeCursor | None,
        limit: int,
        open_only: bool = False,
    ) -> list[OrderListItemDTO]:
        stmt = select(OrderModel).where(OrderModel.organization_id == organization_id)
        if account_id is not None:
            stmt = stmt.where(OrderModel.account_id == account_id)
        if status:
            stmt = stmt.where(OrderModel.status == status)
        if open_only:
            stmt = stmt.where(
                OrderModel.status.in_(
                    [
                        "pending_risk",
                        "approved",
                        "submitted",
                        "partially_filled",
                        "cancel_pending",
                    ]
                )
            )
        if instrument_id is not None:
            stmt = stmt.where(OrderModel.instrument_id == instrument_id)
        if cursor is not None:
            stmt = stmt.where(
                or_(
                    OrderModel.created_at < cursor.before_at,
                    and_(
                        OrderModel.created_at == cursor.before_at,
                        OrderModel.id < cursor.before_id,
                    ),
                )
            )
        stmt = stmt.order_by(OrderModel.created_at.desc(), OrderModel.id.desc()).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        symbols = await self._instruments.get_map([r.instrument_id for r in rows])
        return [
            OrderListItemDTO(
                id=r.id,
                account_id=r.account_id,
                instrument_id=r.instrument_id,
                symbol=symbols[r.instrument_id].symbol if r.instrument_id in symbols else "?",
                side=r.side,
                order_type=r.order_type,
                time_in_force=r.time_in_force,
                quantity=r.quantity,
                limit_price=r.limit_price,
                stop_price=r.stop_price,
                status=r.status,
                filled_quantity=r.filled_quantity,
                average_fill_price=r.average_fill_price,
                rejection_reason=r.rejection_reason,
                source=r.source,
                client_order_id=r.client_order_id,
                strategy_run_id=r.strategy_run_id,
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
            for r in rows
        ]

    async def get_order(
        self, organization_id: TenantId, order_id: UUID
    ) -> tuple[OrderListItemDTO, list[TradeListItemDTO]] | None:
        model = await self._session.get(OrderModel, order_id)
        if model is None or model.organization_id != organization_id:
            return None
        symbols = await self._instruments.get_map([model.instrument_id])
        symbol = symbols[model.instrument_id].symbol if model.instrument_id in symbols else "?"
        order_dto = OrderListItemDTO(
            id=model.id,
            account_id=model.account_id,
            instrument_id=model.instrument_id,
            symbol=symbol,
            side=model.side,
            order_type=model.order_type,
            time_in_force=model.time_in_force,
            quantity=model.quantity,
            limit_price=model.limit_price,
            stop_price=model.stop_price,
            status=model.status,
            filled_quantity=model.filled_quantity,
            average_fill_price=model.average_fill_price,
            rejection_reason=model.rejection_reason,
            source=model.source,
            client_order_id=model.client_order_id,
            strategy_run_id=model.strategy_run_id,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
        executions = (
            (
                await self._session.execute(
                    select(ExecutionModel)
                    .where(ExecutionModel.order_id == order_id)
                    .order_by(ExecutionModel.executed_at)
                )
            )
            .scalars()
            .all()
        )
        trades = [
            TradeListItemDTO(
                id=e.id,
                order_id=e.order_id,
                account_id=e.account_id,
                instrument_id=e.instrument_id,
                symbol=symbol,
                side=e.side,
                quantity=e.quantity,
                price=e.price,
                fee=e.fee,
                fee_currency=e.fee_currency,
                executed_at=e.executed_at,
            )
            for e in executions
        ]
        return order_dto, trades

    async def list_trades(
        self,
        organization_id: TenantId,
        *,
        account_id: UUID | None,
        instrument_id: UUID | None,
        cursor: TimeCursor | None,
        limit: int,
    ) -> list[TradeListItemDTO]:
        stmt = select(ExecutionModel).where(ExecutionModel.organization_id == organization_id)
        if account_id is not None:
            stmt = stmt.where(ExecutionModel.account_id == account_id)
        if instrument_id is not None:
            stmt = stmt.where(ExecutionModel.instrument_id == instrument_id)
        if cursor is not None:
            stmt = stmt.where(
                or_(
                    ExecutionModel.executed_at < cursor.before_at,
                    and_(
                        ExecutionModel.executed_at == cursor.before_at,
                        ExecutionModel.id < cursor.before_id,
                    ),
                )
            )
        stmt = stmt.order_by(ExecutionModel.executed_at.desc(), ExecutionModel.id.desc()).limit(
            limit
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        symbols = await self._instruments.get_map([r.instrument_id for r in rows])
        return [
            TradeListItemDTO(
                id=r.id,
                order_id=r.order_id,
                account_id=r.account_id,
                instrument_id=r.instrument_id,
                symbol=symbols[r.instrument_id].symbol if r.instrument_id in symbols else "?",
                side=r.side,
                quantity=r.quantity,
                price=r.price,
                fee=r.fee,
                fee_currency=r.fee_currency,
                executed_at=r.executed_at,
            )
            for r in rows
        ]

    async def list_positions(
        self,
        organization_id: TenantId,
        *,
        account_id: UUID | None,
        open_only: bool = True,
    ) -> list[PositionListItemDTO]:
        stmt = select(PositionModel).where(PositionModel.organization_id == organization_id)
        if account_id is not None:
            stmt = stmt.where(PositionModel.account_id == account_id)
        if open_only:
            stmt = stmt.where(PositionModel.quantity != 0)
        stmt = stmt.order_by(PositionModel.updated_at.desc())
        rows = (await self._session.execute(stmt)).scalars().all()
        symbols = await self._instruments.get_map([r.instrument_id for r in rows])
        items: list[PositionListItemDTO] = []
        for r in rows:
            mark = r.last_mark if r.last_mark is not None else r.average_price
            unrealized = (mark - r.average_price) * r.quantity if r.quantity != 0 else Decimal("0")
            side = "long" if r.quantity > 0 else ("short" if r.quantity < 0 else "flat")
            items.append(
                PositionListItemDTO(
                    id=r.id,
                    account_id=r.account_id,
                    instrument_id=r.instrument_id,
                    symbol=symbols[r.instrument_id].symbol if r.instrument_id in symbols else "?",
                    side=side,
                    quantity=r.quantity,
                    average_price=r.average_price,
                    last_mark=r.last_mark,
                    market_value=abs(r.quantity) * mark,
                    unrealized_pnl=unrealized,
                    realized_pnl=r.realized_pnl,
                    fees_paid=r.fees_paid,
                    updated_at=r.updated_at,
                )
            )
        return items

    async def count_orders_by_status(self, organization_id: TenantId) -> dict[str, int]:
        result = await self._session.execute(
            select(OrderModel.status, func.count())
            .where(OrderModel.organization_id == organization_id)
            .group_by(OrderModel.status)
        )
        return {str(status): int(count) for status, count in result.tuples().all()}
