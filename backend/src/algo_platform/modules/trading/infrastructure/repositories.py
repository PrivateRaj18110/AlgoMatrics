from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.trading.domain.orders import (
    OPEN_STATUSES,
    Order,
    OrderIntent,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from algo_platform.modules.trading.domain.positions import Execution, Position
from algo_platform.modules.trading.infrastructure.models import (
    ExecutionModel,
    OrderModel,
    PositionModel,
)
from algo_platform.shared.domain.types import (
    AccountId,
    OrderId,
    Side,
    StrategyRunId,
    TenantId,
    utc_now,
)


def order_to_entity(model: OrderModel) -> Order:
    intent = OrderIntent(
        tenant_id=TenantId(model.organization_id),
        account_id=AccountId(model.account_id),
        strategy_run_id=(StrategyRunId(model.strategy_run_id) if model.strategy_run_id else None),
        instrument_id=model.instrument_id,
        side=Side(model.side),
        quantity=model.quantity,
        order_type=OrderType(model.order_type),
        time_in_force=TimeInForce(model.time_in_force),
        client_order_id=model.client_order_id,
        limit_price=model.limit_price,
        stop_price=model.stop_price,
    )
    return Order(
        id=OrderId(model.id),
        intent=intent,
        status=OrderStatus(model.status),
        filled_quantity=model.filled_quantity,
        average_fill_price=model.average_fill_price,
        broker_order_id=model.broker_order_id,
        rejection_reason=model.rejection_reason,
        source=model.source,
        version=model.version,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlOrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, order: Order) -> None:
        intent = order.intent
        self._session.add(
            OrderModel(
                id=order.id,
                organization_id=intent.tenant_id,
                account_id=intent.account_id,
                strategy_run_id=intent.strategy_run_id,
                instrument_id=intent.instrument_id,
                client_order_id=intent.client_order_id,
                broker_order_id=order.broker_order_id,
                side=intent.side.value,
                order_type=intent.order_type.value,
                time_in_force=intent.time_in_force.value,
                quantity=intent.quantity,
                limit_price=intent.limit_price,
                stop_price=intent.stop_price,
                status=order.status.value,
                filled_quantity=order.filled_quantity,
                average_fill_price=order.average_fill_price,
                rejection_reason=order.rejection_reason,
                source=order.source,
                created_at=order.created_at,
                updated_at=order.updated_at,
                version=order.version,
            )
        )
        await self._session.flush()

    async def get(self, organization_id: TenantId, order_id: OrderId) -> Order | None:
        model = await self._session.get(OrderModel, order_id)
        if model is None or model.organization_id != organization_id:
            return None
        return order_to_entity(model)

    async def get_any(self, order_id: OrderId) -> Order | None:
        model = await self._session.get(OrderModel, order_id)
        return order_to_entity(model) if model else None

    async def get_by_client_order_id(
        self, account_id: AccountId, client_order_id: str
    ) -> Order | None:
        result = await self._session.execute(
            select(OrderModel).where(
                OrderModel.account_id == account_id,
                OrderModel.client_order_id == client_order_id,
            )
        )
        model = result.scalar_one_or_none()
        return order_to_entity(model) if model else None

    async def get_by_broker_order_id(self, broker_order_id: str) -> Order | None:
        result = await self._session.execute(
            select(OrderModel).where(OrderModel.broker_order_id == broker_order_id)
        )
        model = result.scalars().first()
        return order_to_entity(model) if model else None

    async def save(self, order: Order) -> None:
        model = await self._session.get(OrderModel, order.id)
        if model is None:
            raise LookupError(f"order {order.id} not found")
        model.status = order.status.value
        model.filled_quantity = order.filled_quantity
        model.average_fill_price = order.average_fill_price
        model.broker_order_id = order.broker_order_id
        model.rejection_reason = order.rejection_reason
        model.updated_at = utc_now()
        model.version = order.version
        await self._session.flush()

    async def list_open_for_account(self, account_id: AccountId) -> list[Order]:
        result = await self._session.execute(
            select(OrderModel).where(
                OrderModel.account_id == account_id,
                OrderModel.status.in_([s.value for s in OPEN_STATUSES]),
            )
        )
        return [order_to_entity(m) for m in result.scalars().all()]

    async def count_open_for_account(self, account_id: AccountId) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(OrderModel)
            .where(
                OrderModel.account_id == account_id,
                OrderModel.status.in_([s.value for s in OPEN_STATUSES]),
            )
        )
        return int(result.scalar_one())


class SqlExecutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, execution: Execution, *, realized_delta: Decimal = Decimal("0")) -> None:
        self._session.add(
            ExecutionModel(
                id=execution.id,
                order_id=execution.order_id,
                organization_id=execution.organization_id,
                account_id=execution.account_id,
                instrument_id=execution.instrument_id,
                side=execution.side.value,
                quantity=execution.quantity,
                price=execution.price,
                fee=execution.fee,
                fee_currency=execution.fee_currency,
                realized_delta=realized_delta,
                executed_at=execution.executed_at,
                broker_execution_id=execution.broker_execution_id,
            )
        )
        await self._session.flush()

    async def exists_broker_execution(self, broker_execution_id: str) -> bool:
        result = await self._session.execute(
            select(func.count())
            .select_from(ExecutionModel)
            .where(ExecutionModel.broker_execution_id == broker_execution_id)
        )
        return int(result.scalar_one()) > 0

    async def list_for_order(self, order_id: OrderId) -> list[ExecutionModel]:
        result = await self._session.execute(
            select(ExecutionModel)
            .where(ExecutionModel.order_id == order_id)
            .order_by(ExecutionModel.executed_at)
        )
        return list(result.scalars().all())

    async def realized_pnl_between(
        self, account_id: AccountId, start: datetime, end: datetime
    ) -> Decimal:
        """Fees paid over a window (realized PnL deltas live on positions)."""
        result = await self._session.execute(
            select(func.coalesce(func.sum(ExecutionModel.fee), 0)).where(
                ExecutionModel.account_id == account_id,
                ExecutionModel.executed_at >= start,
                ExecutionModel.executed_at < end,
            )
        )
        return Decimal(str(result.scalar_one()))


def position_to_entity(model: PositionModel) -> Position:
    return Position(
        id=model.id,
        organization_id=TenantId(model.organization_id),
        account_id=AccountId(model.account_id),
        instrument_id=model.instrument_id,
        quantity=model.quantity,
        average_price=model.average_price,
        realized_pnl=model.realized_pnl,
        fees_paid=model.fees_paid,
        last_mark=model.last_mark,
        opened_at=model.opened_at,
        updated_at=model.updated_at,
        version=model.version,
    )


class SqlPositionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(
        self,
        *,
        organization_id: TenantId,
        account_id: AccountId,
        instrument_id: UUID,
    ) -> Position:
        result = await self._session.execute(
            select(PositionModel).where(
                PositionModel.account_id == account_id,
                PositionModel.instrument_id == instrument_id,
            )
        )
        model = result.scalar_one_or_none()
        if model is not None:
            return position_to_entity(model)
        position = Position.open_empty(
            organization_id=organization_id,
            account_id=account_id,
            instrument_id=instrument_id,
        )
        self._session.add(
            PositionModel(
                id=position.id,
                organization_id=position.organization_id,
                account_id=position.account_id,
                instrument_id=position.instrument_id,
                quantity=position.quantity,
                average_price=position.average_price,
                realized_pnl=position.realized_pnl,
                fees_paid=position.fees_paid,
                last_mark=position.last_mark,
                opened_at=position.opened_at,
                updated_at=position.updated_at,
                version=position.version,
            )
        )
        await self._session.flush()
        return position

    async def save(self, position: Position) -> None:
        model = await self._session.get(PositionModel, position.id)
        if model is None:
            raise LookupError(f"position {position.id} not found")
        model.quantity = position.quantity
        model.average_price = position.average_price
        model.realized_pnl = position.realized_pnl
        model.fees_paid = position.fees_paid
        model.last_mark = position.last_mark
        model.updated_at = utc_now()
        model.version = position.version
        await self._session.flush()

    async def list_for_account(
        self, account_id: AccountId, *, open_only: bool = True
    ) -> list[Position]:
        stmt = select(PositionModel).where(PositionModel.account_id == account_id)
        if open_only:
            stmt = stmt.where(PositionModel.quantity != 0)
        result = await self._session.execute(stmt)
        return [position_to_entity(m) for m in result.scalars().all()]

    async def list_for_organization(
        self, organization_id: TenantId, *, open_only: bool = True
    ) -> list[Position]:
        stmt = select(PositionModel).where(PositionModel.organization_id == organization_id)
        if open_only:
            stmt = stmt.where(PositionModel.quantity != 0)
        result = await self._session.execute(stmt)
        return [position_to_entity(m) for m in result.scalars().all()]

    async def count_open_for_account(self, account_id: AccountId) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(PositionModel)
            .where(PositionModel.account_id == account_id, PositionModel.quantity != 0)
        )
        return int(result.scalar_one())

    async def gross_exposure_for_account(self, account_id: AccountId) -> Decimal:
        result = await self._session.execute(
            select(
                func.coalesce(
                    func.sum(
                        func.abs(PositionModel.quantity)
                        * func.coalesce(PositionModel.last_mark, PositionModel.average_price)
                    ),
                    0,
                )
            ).where(PositionModel.account_id == account_id)
        )
        return Decimal(str(result.scalar_one()))

    async def realized_pnl_for_account(self, account_id: AccountId) -> Decimal:
        result = await self._session.execute(
            select(func.coalesce(func.sum(PositionModel.realized_pnl), 0)).where(
                PositionModel.account_id == account_id
            )
        )
        return Decimal(str(result.scalar_one()))
