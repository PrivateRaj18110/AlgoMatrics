"""Live-order router: builds venue adapters per connection and applies updates.

Used by the trading-engine process for accounts in live mode. Adapters are
cached per broker connection; each connection gets one background poller that
normalizes venue updates into the same order/execution/position pipeline the
paper engine uses. Broker timeouts are treated as unknown outcomes: the order
stays open until the poller reconciles its terminal state.
"""

from __future__ import annotations

import asyncio
import contextlib
import secrets
from collections.abc import Awaitable, Callable
from decimal import Decimal
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from algo_platform.modules.brokerage.application.service import (
    decrypt_connection_credentials,
)
from algo_platform.modules.brokerage.infrastructure.repositories import (
    SqlBrokerConnectionRepository,
    SqlTradingAccountRepository,
)
from algo_platform.modules.instruments.application.venue_directory import (
    VenueInstrumentDirectory,
)
from algo_platform.modules.notifications.application.service import NotificationService
from algo_platform.modules.trading.application.broker_port import (
    BrokerExecutionPort,
    BrokerOrderUpdate,
)
from algo_platform.modules.trading.domain.orders import Order, OrderStatus
from algo_platform.modules.trading.domain.positions import Execution
from algo_platform.modules.trading.infrastructure.brokers.angelone import (
    AngelOneExecutionAdapter,
)
from algo_platform.modules.trading.infrastructure.brokers.binance import (
    BinanceExecutionAdapter,
)
from algo_platform.modules.trading.infrastructure.brokers.delta import (
    DeltaExecutionAdapter,
)
from algo_platform.modules.trading.infrastructure.brokers.ibkr import (
    IbkrExecutionAdapter,
)
from algo_platform.modules.trading.infrastructure.brokers.indian import VenueInstrument
from algo_platform.modules.trading.infrastructure.brokers.mt5 import (
    Mt5AgentExecutionAdapter,
)
from algo_platform.modules.trading.infrastructure.brokers.zerodha import (
    ZerodhaExecutionAdapter,
)
from algo_platform.modules.trading.infrastructure.repositories import (
    SqlExecutionRepository,
    SqlOrderRepository,
    SqlPositionRepository,
)
from algo_platform.shared.domain.errors import DomainError, NotFoundError
from algo_platform.shared.domain.types import AccountId, OrderId
from algo_platform.shared.infrastructure.encryption import CredentialCipher
from algo_platform.shared.infrastructure.outbox import enqueue_event
from algo_platform.shared.infrastructure.redis_gateway import RedisGateway

logger = structlog.get_logger("live_router")


class LiveRouter:
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        redis: RedisGateway,
        cipher: CredentialCipher,
        mt5_allowed_hosts: list[str] | None = None,
        mt5_require_https: bool = False,
    ) -> None:
        self._session_factory = session_factory
        self._redis = redis
        self._cipher = cipher
        self._mt5_allowed_hosts = (
            frozenset(host.strip().lower() for host in mt5_allowed_hosts if host.strip())
            if mt5_allowed_hosts is not None
            else None
        )
        self._mt5_require_https = mt5_require_https
        self._adapters: dict[UUID, BrokerExecutionPort] = {}
        self._pollers: dict[UUID, asyncio.Task[None]] = {}

    async def shutdown(self) -> None:
        for task in self._pollers.values():
            task.cancel()
        for task in self._pollers.values():
            with contextlib.suppress(asyncio.CancelledError):
                await task
        for adapter in self._adapters.values():
            with contextlib.suppress(Exception):
                await adapter.disconnect()
        self._adapters.clear()
        self._pollers.clear()

    # -- commands -------------------------------------------------------------

    async def submit(self, order_id: UUID) -> None:
        async with self._session_factory() as session:
            orders = SqlOrderRepository(session)
            order = await orders.get_any(OrderId(order_id))
            if order is None or order.status is not OrderStatus.APPROVED:
                return
            try:
                adapter, _connection_id = await self._adapter_for_account(
                    session, order.intent.account_id
                )
                ack = await adapter.submit_order(order.intent)
                order.mark_submitted(ack.broker_order_id)
            except DomainError as error:
                order.reject(f"broker: {error.message}")
                logger.warning("live.submit_rejected", order_id=str(order_id), error=error.message)
            except Exception as error:
                logger.exception("live.submit_unknown_outcome", order_id=str(order_id))
                order.mark_submitted(f"unknown-{secrets.token_hex(6)}")
                order.rejection_reason = f"unknown outcome: {type(error).__name__}"
            await orders.save(order)
            for event in order.events:
                await enqueue_event(
                    session,
                    event=event,
                    aggregate_type="order",
                    payload={"order_id": str(order.id), "status": order.status.value},
                )
            await session.commit()
        await self._publish_order(order)

    async def cancel(self, order_id: UUID) -> None:
        async with self._session_factory() as session:
            orders = SqlOrderRepository(session)
            order = await orders.get_any(OrderId(order_id))
            if order is None or order.broker_order_id is None:
                return
            try:
                adapter, _ = await self._adapter_for_account(session, order.intent.account_id)
                await adapter.cancel_order(order.broker_order_id)
            except DomainError as error:
                logger.warning("live.cancel_failed", order_id=str(order_id), error=error.message)
            await session.commit()

    # -- adapter management -------------------------------------------------------

    async def _adapter_for_account(
        self, session: AsyncSession, account_id: UUID
    ) -> tuple[BrokerExecutionPort, UUID]:
        accounts = SqlTradingAccountRepository(session)
        account = await accounts.get_any(AccountId(account_id))
        if account is None:
            raise NotFoundError("trading account not found")
        connection_id = account.connection_id
        cached = self._adapters.get(connection_id)
        if cached is not None:
            return cached, connection_id

        connections = SqlBrokerConnectionRepository(session)
        connection = await connections.get_any(connection_id)
        if connection is None:
            raise NotFoundError("broker connection not found")
        credentials = decrypt_connection_credentials(self._cipher, connection)
        resolver = self._make_symbol_resolver(connection.broker_id)
        adapter: BrokerExecutionPort
        if connection.broker_code == "zerodha":
            adapter = ZerodhaExecutionAdapter(
                api_key=credentials.get("api_key", ""),
                access_token=credentials.get("access_token", ""),
                symbol_resolver=resolver,
            )
        elif connection.broker_code == "angelone":
            adapter = AngelOneExecutionAdapter(
                api_key=credentials.get("api_key", ""),
                jwt_token=credentials.get("jwt_token", ""),
                client_code=credentials.get("client_code", ""),
                symbol_resolver=resolver,
            )
        elif connection.broker_code == "delta":
            adapter = DeltaExecutionAdapter(
                api_key=credentials.get("api_key", ""),
                api_secret=credentials.get("api_secret", ""),
                symbol_resolver=resolver,
            )
        elif connection.broker_code == "binance":
            adapter = BinanceExecutionAdapter(
                api_key=credentials.get("api_key", ""),
                api_secret=credentials.get("api_secret", ""),
                symbol_resolver=resolver,
            )
        elif connection.broker_code == "interactive_brokers":
            adapter = IbkrExecutionAdapter(
                gateway_url=credentials.get("gateway_url", ""),
                account_id=credentials.get("account_id", ""),
                symbol_resolver=resolver,
            )
        elif connection.broker_code == "mt5":
            adapter = Mt5AgentExecutionAdapter(
                agent_url=credentials.get("agent_url", ""),
                agent_token=credentials.get("agent_token", ""),
                symbol_resolver=resolver,
                allowed_hosts=self._mt5_allowed_hosts,
                require_https=self._mt5_require_https,
            )
        else:
            raise NotFoundError(f"no live execution adapter for broker '{connection.broker_code}'")
        await adapter.connect()
        self._adapters[connection_id] = adapter
        self._pollers[connection_id] = asyncio.create_task(
            self._poll_updates(connection_id, adapter),
            name=f"live-poller-{connection_id}",
        )
        logger.info(
            "live.adapter_connected",
            connection_id=str(connection_id),
            broker=connection.broker_code,
        )
        return adapter, connection_id

    def _make_symbol_resolver(
        self, broker_id: UUID
    ) -> Callable[[UUID], Awaitable[VenueInstrument]]:
        session_factory = self._session_factory

        async def resolve(instrument_id: UUID) -> VenueInstrument:
            async with session_factory() as session:
                summary = await VenueInstrumentDirectory(session).resolve(
                    broker_id=broker_id,
                    instrument_id=instrument_id,
                )
                return VenueInstrument(
                    symbol=summary.venue_symbol,
                    exchange=summary.exchange,
                    lot_size=summary.lot_size,
                    token=summary.instrument_token or "",
                )

        return resolve

    # -- update pipeline ---------------------------------------------------------------

    async def _poll_updates(self, connection_id: UUID, adapter: BrokerExecutionPort) -> None:
        try:
            async for update in adapter.stream_order_updates():
                try:
                    await self._apply_update(update)
                except Exception:
                    logger.exception(
                        "live.update_apply_failed", broker_order=update.broker_order_id
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("live.poller_crashed", connection_id=str(connection_id))
            self._adapters.pop(connection_id, None)
            self._pollers.pop(connection_id, None)

    async def _apply_update(self, update: BrokerOrderUpdate) -> None:
        async with self._session_factory() as session:
            orders = SqlOrderRepository(session)
            order = await orders.get_by_broker_order_id(update.broker_order_id)
            if order is None:
                return
            fill_delta = update.filled_quantity - order.filled_quantity
            realized_delta = Decimal("0")
            if fill_delta > 0 and update.average_price is not None:
                order.apply_fill(fill_delta, update.average_price)
                positions = SqlPositionRepository(session)
                position = await positions.get_or_create(
                    organization_id=order.intent.tenant_id,
                    account_id=order.intent.account_id,
                    instrument_id=order.intent.instrument_id,
                )
                realized_delta = position.apply_execution(
                    order.intent.side, fill_delta, update.average_price, Decimal("0")
                )
                position.mark(update.average_price)
                await positions.save(position)
                execution = Execution.record(
                    order_id=order.id,
                    organization_id=order.intent.tenant_id,
                    account_id=order.intent.account_id,
                    instrument_id=order.intent.instrument_id,
                    side=order.intent.side,
                    quantity=fill_delta,
                    price=update.average_price,
                    fee=Decimal("0"),
                    fee_currency="INR",
                    broker_execution_id=(f"{update.broker_order_id}-{update.filled_quantity}"),
                    executed_at=update.occurred_at,
                )
                await SqlExecutionRepository(session).add(execution, realized_delta=realized_delta)
            elif update.status is OrderStatus.CANCELLED and order.is_open:
                order.confirm_cancelled()
            elif update.status is OrderStatus.REJECTED and order.is_open:
                order.reject(update.raw_reference or "rejected by venue")
            await orders.save(order)
            for event in order.events:
                await enqueue_event(
                    session,
                    event=event,
                    aggregate_type="order",
                    payload={"order_id": str(order.id), "status": order.status.value},
                )
            if order.status is OrderStatus.FILLED:
                await NotificationService(session, self._redis).notify(
                    organization_id=order.intent.tenant_id,
                    title=f"Live order filled: {order.intent.side.value} {order.intent.quantity}",
                    body=f"Average price {order.average_fill_price}",
                    type_="order_fill",
                    severity="success",
                    payload={"order_id": str(order.id)},
                )
            await session.commit()
        await self._publish_order(order)

    async def _publish_order(self, order: Order) -> None:
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
