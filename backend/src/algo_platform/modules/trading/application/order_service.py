"""Order placement and cancellation: the guarded write path.

Every order passes entitlement, kill-switch, and pre-trade risk gates; the
approved order plus its outbox events commit in one transaction, and an
execution command is pushed to the engine stream afterwards.
"""

from __future__ import annotations

import secrets
from decimal import Decimal
from uuid import UUID

import structlog
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.billing.application.service import SubscriptionService
from algo_platform.modules.brokerage.domain.brokers import AccountStatus, TradingAccount
from algo_platform.modules.brokerage.infrastructure.repositories import (
    SqlBrokerConnectionRepository,
    SqlTradingAccountRepository,
)
from algo_platform.modules.instruments.application.directory import InstrumentDirectory
from algo_platform.modules.instruments.application.venue_directory import (
    VenueInstrumentDirectory,
)
from algo_platform.modules.organizations.application.policy import OrganizationPolicy
from algo_platform.modules.risk.application.service import OrderRiskInput, RiskService
from algo_platform.modules.risk.domain.limits import RiskDecisionResult
from algo_platform.modules.trading.domain.orders import (
    Order,
    OrderIntent,
    OrderType,
    TimeInForce,
)
from algo_platform.modules.trading.infrastructure.repositories import (
    SqlOrderRepository,
    SqlPositionRepository,
)
from algo_platform.shared.domain.errors import (
    ConflictError,
    NotFoundError,
    ValidationFailed,
)
from algo_platform.shared.domain.types import (
    AccountId,
    OrderId,
    Side,
    StrategyRunId,
    TenantId,
    utc_now,
)
from algo_platform.shared.infrastructure.outbox import enqueue_engine_command, enqueue_event
from algo_platform.shared.infrastructure.redis_gateway import RedisGateway

logger = structlog.get_logger(__name__)

LAST_PRICES_KEY = "md:last"


def daily_pnl_key(account_id: AccountId) -> str:
    return f"pnl:day:{account_id}:{utc_now():%Y%m%d}"


class OrderService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        redis: RedisGateway,
        billing: SubscriptionService,
        risk: RiskService,
    ) -> None:
        self._session = session
        self._redis = redis
        self._billing = billing
        self._risk = risk
        self._orders = SqlOrderRepository(session)
        self._positions = SqlPositionRepository(session)
        self._accounts = SqlTradingAccountRepository(session)
        self._instruments = InstrumentDirectory(session)

    async def place_order(
        self,
        organization_id: TenantId,
        *,
        account_id: AccountId,
        instrument_id: UUID,
        side: Side,
        quantity: Decimal,
        order_type: OrderType,
        time_in_force: TimeInForce,
        limit_price: Decimal | None,
        stop_price: Decimal | None,
        client_order_id: str | None,
        strategy_run_id: StrategyRunId | None = None,
        source: str = "manual",
    ) -> Order:
        account = await self._accounts.get(organization_id, account_id)
        if account is None:
            raise NotFoundError("trading account not found")
        if account.status is not AccountStatus.ACTIVE:
            raise ConflictError("trading account is closed")

        instrument = await self._instruments.get(instrument_id)
        if instrument is None:
            raise NotFoundError("instrument not found")
        if account.mode.value == "live":
            if not await OrganizationPolicy(self._session).live_trading_enabled(organization_id):
                raise ConflictError("live trading is disabled in organization settings")
            connection = await SqlBrokerConnectionRepository(self._session).get(
                organization_id, account.connection_id
            )
            if connection is None or connection.status.value != "verified":
                raise ConflictError("the live broker connection is not verified")
            await VenueInstrumentDirectory(self._session).resolve(
                broker_id=connection.broker_id,
                instrument_id=instrument_id,
            )

        # Idempotency under concurrency: serialize placements that share a
        # (account, client_order_id) with a transaction-scoped advisory lock,
        # then re-check. This makes a duplicate submit return the original
        # order instead of racing into the unique-constraint violation.
        effective_client_id = client_order_id or f"ord-{secrets.token_hex(10)}"
        await self._acquire_order_lock(account_id, effective_client_id)
        existing = await self._orders.get_by_client_order_id(account_id, effective_client_id)
        if existing is not None:
            return existing

        intent = OrderIntent(
            tenant_id=organization_id,
            account_id=account_id,
            strategy_run_id=strategy_run_id,
            instrument_id=instrument_id,
            side=side,
            quantity=quantity,
            order_type=order_type,
            time_in_force=time_in_force,
            client_order_id=effective_client_id,
            limit_price=limit_price,
            stop_price=stop_price,
        )
        order = Order.place(intent, source=source)

        limits = await self._billing.current_limits(organization_id)
        orders_today = await self._billing.orders_placed_today(organization_id)
        estimated_price = await self._estimate_price(instrument_id, limit_price)
        realized_today = await self._realized_pnl_today(account_id)
        open_positions = await self._positions.count_open_for_account(account_id)
        exposure = await self._positions.gross_exposure_for_account(account_id)

        decision = await self._risk.evaluate_order(
            OrderRiskInput(
                organization_id=organization_id,
                account_id=account_id,
                order_id=order.id,
                quantity=quantity,
                estimated_price=estimated_price,
                orders_today=orders_today,
                max_orders_per_day=limits.max_orders_per_day,
                realized_pnl_today=realized_today,
                open_positions=open_positions,
                gross_exposure=exposure,
                account_equity=account.equity,
                account_starting_balance=account.starting_balance,
            )
        )
        if decision.result is RiskDecisionResult.APPROVED:
            order.approve()
        else:
            order.reject("risk: " + ", ".join(decision.reason_codes))

        await self._orders.add(order)
        for event in order.events:
            await enqueue_event(
                self._session,
                event=event,
                aggregate_type="order",
                payload=self._order_event_payload(order),
            )
        order.events.clear()
        await self._billing.record_usage(organization_id, metric="orders_placed")

        if order.status.value == "approved":
            await enqueue_engine_command(
                self._session,
                command_type="submit_order",
                aggregate_type="order",
                aggregate_id=order.id,
                organization_id=organization_id,
                payload={
                    "order_id": str(order.id),
                    "organization_id": str(organization_id),
                    "account_id": str(account_id),
                    "mode": account.mode.value,
                },
            )
        logger.info(
            "trading.order_placed",
            order_id=str(order.id),
            status=order.status.value,
            source=source,
        )
        return order

    async def cancel_order(self, organization_id: TenantId, order_id: OrderId) -> Order:
        order = await self._orders.get(organization_id, order_id)
        if order is None:
            raise NotFoundError("order not found")
        order.request_cancel()
        await self._orders.save(order)
        for event in order.events:
            await enqueue_event(
                self._session,
                event=event,
                aggregate_type="order",
                payload=self._order_event_payload(order),
            )
        order.events.clear()
        await enqueue_engine_command(
            self._session,
            command_type="cancel_order",
            aggregate_type="order",
            aggregate_id=order.id,
            organization_id=organization_id,
            payload={
                "order_id": str(order.id),
                "organization_id": str(organization_id),
                "account_id": str(order.intent.account_id),
            },
        )
        return order

    async def _acquire_order_lock(self, account_id: AccountId, client_order_id: str) -> None:
        # Transaction-scoped advisory lock keyed by (account, client id); auto
        # released at commit/rollback. Only serializes the same key, so unrelated
        # orders proceed concurrently. Skips on non-PostgreSQL backends.
        if self._session.get_bind().dialect.name != "postgresql":
            return
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))").bindparams(
                bindparam("key", f"{account_id}:{client_order_id}")
            ),
        )

    async def _estimate_price(self, instrument_id: UUID, limit_price: Decimal | None) -> Decimal:
        if limit_price is not None:
            return limit_price
        tick = await self._redis.hget_json(LAST_PRICES_KEY, str(instrument_id))
        if tick is not None and tick.get("last"):
            return Decimal(str(tick["last"]))
        instrument = await self._instruments.get(instrument_id)
        if instrument is None:
            raise ValidationFailed("cannot estimate a price for an unknown instrument")
        return instrument.reference_price

    async def _realized_pnl_today(self, account_id: AccountId) -> Decimal:
        raw = await self._redis.get_str(daily_pnl_key(account_id))
        if raw is None:
            return Decimal("0")
        try:
            return Decimal(raw)
        except ArithmeticError:
            return Decimal("0")

    @staticmethod
    def _order_event_payload(order: Order) -> dict[str, object]:
        return {
            "order_id": str(order.id),
            "account_id": str(order.intent.account_id),
            "instrument_id": str(order.intent.instrument_id),
            "side": order.intent.side.value,
            "quantity": str(order.intent.quantity),
            "status": order.status.value,
            "filled_quantity": str(order.filled_quantity),
        }


async def get_trading_account_or_raise(
    session: AsyncSession, organization_id: TenantId, account_id: AccountId
) -> TradingAccount:
    account = await SqlTradingAccountRepository(session).get(organization_id, account_id)
    if account is None:
        raise NotFoundError("trading account not found")
    return account
