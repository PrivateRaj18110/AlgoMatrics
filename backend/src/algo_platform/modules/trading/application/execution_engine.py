"""Paper execution engine: order matching, fills, positions, and projections.

Runs inside the trading-engine process. Consumes ticks, evaluates open paper
orders with the deterministic simulator, and commits order/execution/position/
account changes plus outbox events in one transaction per fill. Live-account
orders are routed through broker adapters by the LiveRouter (separate class);
this engine owns only the simulated venue.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from algo_platform.modules.brokerage.infrastructure.models import TradingAccountModel
from algo_platform.modules.notifications.application.service import NotificationService
from algo_platform.modules.trading.application.order_service import daily_pnl_key
from algo_platform.modules.trading.domain.orders import Order, OrderStatus, OrderType
from algo_platform.modules.trading.domain.positions import Execution
from algo_platform.modules.trading.infrastructure.brokers.paper import (
    PaperExecutionSimulator,
    PaperMarketState,
)
from algo_platform.modules.trading.infrastructure.models import OrderModel, PositionModel
from algo_platform.modules.trading.infrastructure.repositories import (
    SqlExecutionRepository,
    SqlOrderRepository,
    SqlPositionRepository,
    order_to_entity,
)
from algo_platform.shared.domain.types import AccountId, OrderId, Side, utc_now
from algo_platform.shared.infrastructure.outbox import enqueue_event
from algo_platform.shared.infrastructure.redis_gateway import RedisGateway

logger = structlog.get_logger("execution_engine")


@dataclass(slots=True)
class OpenPaperOrder:
    order_id: UUID
    organization_id: UUID
    account_id: UUID
    instrument_id: UUID
    side: Side
    order_type: OrderType
    quantity: Decimal
    filled_quantity: Decimal
    limit_price: Decimal | None
    stop_price: Decimal | None
    stop_armed: bool = False
    fill_round: int = 0

    @property
    def remaining(self) -> Decimal:
        return self.quantity - self.filled_quantity


class PaperExecutionEngine:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        redis: RedisGateway,
        simulator: PaperExecutionSimulator,
    ) -> None:
        self._session_factory = session_factory
        self._redis = redis
        self._simulator = simulator
        self._open_orders: dict[UUID, OpenPaperOrder] = {}
        self._orders_by_instrument: dict[UUID, set[UUID]] = {}

    @property
    def open_order_count(self) -> int:
        return len(self._open_orders)

    # -- recovery -----------------------------------------------------------------

    async def recover(self) -> None:
        """Reload open paper orders after a restart."""
        async with self._session_factory() as session:
            stmt = (
                select(OrderModel, TradingAccountModel.mode)
                .join(
                    TradingAccountModel,
                    TradingAccountModel.id == OrderModel.account_id,
                )
                .where(
                    OrderModel.status.in_(
                        ["approved", "submitted", "partially_filled", "cancel_pending"]
                    )
                )
            )
            rows = (await session.execute(stmt)).all()
            submitted = 0
            for model, mode in rows:
                if mode != "paper":
                    continue
                if model.status == "cancel_pending":
                    order = order_to_entity(model)
                    order.confirm_cancelled()
                    await SqlOrderRepository(session).save(order)
                    continue
                if model.status == "approved":
                    order = order_to_entity(model)
                    order.mark_submitted(f"paper-{secrets.token_hex(8)}")
                    await SqlOrderRepository(session).save(order)
                self._track(model)
                submitted += 1
            await session.commit()
        logger.info("engine.recovered", open_orders=submitted)

    def _track(self, model: OrderModel) -> None:
        record = OpenPaperOrder(
            order_id=model.id,
            organization_id=model.organization_id,
            account_id=model.account_id,
            instrument_id=model.instrument_id,
            side=Side(model.side),
            order_type=OrderType(model.order_type),
            quantity=model.quantity,
            filled_quantity=model.filled_quantity,
            limit_price=model.limit_price,
            stop_price=model.stop_price,
        )
        self._open_orders[model.id] = record
        self._orders_by_instrument.setdefault(model.instrument_id, set()).add(model.id)

    def _untrack(self, order_id: UUID, instrument_id: UUID) -> None:
        self._open_orders.pop(order_id, None)
        bucket = self._orders_by_instrument.get(instrument_id)
        if bucket is not None:
            bucket.discard(order_id)
            if not bucket:
                self._orders_by_instrument.pop(instrument_id, None)

    # -- commands ------------------------------------------------------------------

    async def handle_submit(self, order_id: UUID) -> None:
        async with self._session_factory() as session:
            model = await session.get(OrderModel, order_id)
            if model is None or model.status not in {"approved", "pending_risk"}:
                return
            order = order_to_entity(model)
            if order.status is not OrderStatus.APPROVED:
                return
            order.mark_submitted(f"paper-{secrets.token_hex(8)}")
            await SqlOrderRepository(session).save(order)
            for event in order.events:
                await enqueue_event(
                    session,
                    event=event,
                    aggregate_type="order",
                    payload={"order_id": str(order.id), "status": order.status.value},
                )
            await session.commit()
            self._track(model)
        await self._publish_order_update(order)

    async def handle_cancel(self, order_id: UUID) -> None:
        async with self._session_factory() as session:
            model = await session.get(OrderModel, order_id)
            if model is None:
                return
            if model.status not in {"cancel_pending", "submitted", "partially_filled"}:
                return
            order = order_to_entity(model)
            order.confirm_cancelled()
            await SqlOrderRepository(session).save(order)
            for event in order.events:
                await enqueue_event(
                    session,
                    event=event,
                    aggregate_type="order",
                    payload={"order_id": str(order.id), "status": order.status.value},
                )
            await session.commit()
        self._untrack(order_id, model.instrument_id)
        await self._publish_order_update(order)

    # -- tick processing ---------------------------------------------------------------

    async def on_tick(self, instrument_id: UUID, bid: Decimal, ask: Decimal) -> list[UUID]:
        """Evaluate open orders for one instrument; returns touched account ids."""
        order_ids = list(self._orders_by_instrument.get(instrument_id, ()))
        touched_accounts: list[UUID] = []
        market = PaperMarketState(bid=bid, ask=ask)
        for order_id in order_ids:
            record = self._open_orders.get(order_id)
            if record is None:
                continue
            fill, stop_armed = self._simulator.evaluate(
                order_id=record.order_id,
                side=record.side,
                order_type=record.order_type,
                remaining_quantity=record.remaining,
                limit_price=record.limit_price,
                stop_price=record.stop_price,
                stop_armed=record.stop_armed,
                market=market,
                fill_round=record.fill_round,
            )
            record.stop_armed = stop_armed
            if fill is None:
                continue
            record.fill_round += 1
            applied = await self._apply_fill(
                record, quantity=fill.quantity, price=fill.price, fee=fill.fee
            )
            if applied:
                touched_accounts.append(record.account_id)
                record.filled_quantity += fill.quantity
                if record.remaining <= 0:
                    self._untrack(record.order_id, record.instrument_id)
        return touched_accounts

    async def _apply_fill(
        self, record: OpenPaperOrder, *, quantity: Decimal, price: Decimal, fee: Decimal
    ) -> bool:
        async with self._session_factory() as session:
            orders = SqlOrderRepository(session)
            order = await orders.get_any(OrderId(record.order_id))
            if order is None or order.status not in {
                OrderStatus.SUBMITTED,
                OrderStatus.PARTIALLY_FILLED,
                OrderStatus.CANCEL_PENDING,
            }:
                self._untrack(record.order_id, record.instrument_id)
                return False
            quantity = min(quantity, order.remaining_quantity)
            if quantity <= 0:
                self._untrack(record.order_id, record.instrument_id)
                return False

            order.apply_fill(quantity, price)
            await orders.save(order)

            positions = SqlPositionRepository(session)
            position = await positions.get_or_create(
                organization_id=order.intent.tenant_id,
                account_id=order.intent.account_id,
                instrument_id=order.intent.instrument_id,
            )
            realized_delta = position.apply_execution(order.intent.side, quantity, price, fee)
            position.mark(price)
            await positions.save(position)

            execution = Execution.record(
                order_id=order.id,
                organization_id=order.intent.tenant_id,
                account_id=order.intent.account_id,
                instrument_id=order.intent.instrument_id,
                side=order.intent.side,
                quantity=quantity,
                price=price,
                fee=fee,
                fee_currency="INR",
                broker_execution_id=f"paper-x-{secrets.token_hex(10)}",
            )
            await SqlExecutionRepository(session).add(execution, realized_delta=realized_delta)

            account = await session.get(TradingAccountModel, order.intent.account_id)
            if account is not None:
                notional = quantity * price
                if order.intent.side is Side.BUY:
                    account.cash_balance = account.cash_balance - notional - fee
                else:
                    account.cash_balance = account.cash_balance + notional - fee
                account.updated_at = utc_now()

            for event in order.events:
                await enqueue_event(
                    session,
                    event=event,
                    aggregate_type="order",
                    payload={
                        "order_id": str(order.id),
                        "status": order.status.value,
                        "filled_quantity": str(order.filled_quantity),
                        "fill_price": str(price),
                    },
                )
            if order.status is OrderStatus.FILLED:
                await NotificationService(session, self._redis).notify(
                    organization_id=order.intent.tenant_id,
                    title=f"Order filled: {order.intent.side.value} {order.intent.quantity}",
                    body=f"Average price {order.average_fill_price}",
                    type_="order_fill",
                    severity="success",
                    payload={"order_id": str(order.id)},
                )
            await session.commit()

        await self._bump_daily_pnl(AccountId(record.account_id), realized_delta)
        await self._publish_order_update(order)
        await self._redis.publish_json(
            f"positions:{record.organization_id}",
            {
                "channel": "positions",
                "account_id": str(record.account_id),
                "instrument_id": str(record.instrument_id),
                "quantity": str(position.quantity),
                "average_price": str(position.average_price),
                "realized_pnl": str(position.realized_pnl),
            },
        )
        return True

    async def _bump_daily_pnl(self, account_id: AccountId, delta: Decimal) -> None:
        if delta == 0:
            return
        key = daily_pnl_key(account_id)
        current = await self._redis.get_str(key)
        try:
            total = Decimal(current) if current else Decimal("0")
        except ArithmeticError:
            total = Decimal("0")
        await self._redis.set_str(key, str(total + delta), ttl_seconds=60 * 60 * 36)

    async def _publish_order_update(self, order: Order) -> None:
        await self._redis.publish_json(
            f"orders:{order.intent.tenant_id}",
            {
                "channel": "orders",
                "order_id": str(order.id),
                "account_id": str(order.intent.account_id),
                "instrument_id": str(order.intent.instrument_id),
                "side": order.intent.side.value,
                "status": order.status.value,
                "filled_quantity": str(order.filled_quantity),
                "average_fill_price": str(order.average_fill_price)
                if order.average_fill_price is not None
                else None,
            },
        )

    # -- marks / equity / snapshots -------------------------------------------------------

    async def refresh_marks_and_equity(self, last_prices: dict[str, dict[str, Any]]) -> None:
        """Update position marks and account equity from the latest quotes."""
        async with self._session_factory() as session:
            positions = (
                (await session.execute(select(PositionModel).where(PositionModel.quantity != 0)))
                .scalars()
                .all()
            )
            account_values: dict[UUID, Decimal] = {}
            org_by_account: dict[UUID, UUID] = {}
            for position in positions:
                quote = last_prices.get(str(position.instrument_id))
                if quote and quote.get("last"):
                    position.last_mark = Decimal(str(quote["last"]))
                    position.updated_at = utc_now()
                mark = (
                    position.last_mark if position.last_mark is not None else position.average_price
                )
                account_values[position.account_id] = (
                    account_values.get(position.account_id, Decimal("0")) + position.quantity * mark
                )
                org_by_account[position.account_id] = position.organization_id

            accounts = (
                (
                    await session.execute(
                        select(TradingAccountModel).where(
                            TradingAccountModel.status == "active",
                            TradingAccountModel.mode == "paper",
                        )
                    )
                )
                .scalars()
                .all()
            )
            for account in accounts:
                market_value = account_values.get(account.id, Decimal("0"))
                account.equity = account.cash_balance + market_value
                account.updated_at = utc_now()
                org_by_account.setdefault(account.id, account.organization_id)
            await session.commit()

        for account in accounts:
            await self._redis.publish_json(
                f"portfolio:{account.organization_id}",
                {
                    "channel": "portfolio",
                    "account_id": str(account.id),
                    "equity": str(account.equity),
                    "cash": str(account.cash_balance),
                },
            )

    async def write_snapshots(self) -> None:
        from algo_platform.modules.portfolio.infrastructure.models import (
            PortfolioSnapshotModel,
        )

        async with self._session_factory() as session:
            accounts = (
                (
                    await session.execute(
                        select(TradingAccountModel).where(TradingAccountModel.status == "active")
                    )
                )
                .scalars()
                .all()
            )
            for account in accounts:
                positions = (
                    (
                        await session.execute(
                            select(PositionModel).where(PositionModel.account_id == account.id)
                        )
                    )
                    .scalars()
                    .all()
                )
                realized = sum((p.realized_pnl for p in positions), Decimal("0"))
                unrealized = Decimal("0")
                exposure = Decimal("0")
                open_count = 0
                for p in positions:
                    if p.quantity == 0:
                        continue
                    open_count += 1
                    mark = p.last_mark if p.last_mark is not None else p.average_price
                    unrealized += (mark - p.average_price) * p.quantity
                    exposure += abs(p.quantity) * mark
                session.add(
                    PortfolioSnapshotModel(
                        organization_id=account.organization_id,
                        account_id=account.id,
                        as_of=utc_now(),
                        equity=account.equity,
                        cash=account.cash_balance,
                        realized_pnl=realized,
                        unrealized_pnl=unrealized,
                        exposure=exposure,
                        open_positions=open_count,
                    )
                )
            await session.commit()
