"""End-to-end paper vertical slice.

register → create org → connect paper account → place order → paper fill →
position → realized P&L. Exercised at the application/engine layer against a
real PostgreSQL + Redis, mirroring the order path from FOUNDATION.md.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from algo_platform.modules.billing.application.service import SubscriptionService
from algo_platform.modules.billing.infrastructure.models import PlanModel
from algo_platform.modules.brokerage.application.service import BrokerageService
from algo_platform.modules.brokerage.infrastructure.models import BrokerModel
from algo_platform.modules.brokerage.infrastructure.repositories import (
    SqlBrokerCatalogRepository,
    SqlBrokerConnectionRepository,
    SqlTradingAccountRepository,
)
from algo_platform.modules.brokerage.infrastructure.verifiers import build_verifier_registry
from algo_platform.modules.identity.application.directory import UserDirectory
from algo_platform.modules.identity.domain.users import User
from algo_platform.modules.identity.infrastructure.repositories import SqlUserRepository
from algo_platform.modules.instruments.infrastructure.models import InstrumentModel
from algo_platform.modules.organizations.application.service import OrganizationService
from algo_platform.modules.organizations.infrastructure.repositories import (
    SqlInvitationRepository,
    SqlMembershipRepository,
    SqlOrganizationRepository,
)
from algo_platform.modules.risk.application.service import RiskService
from algo_platform.modules.trading.application.execution_engine import PaperExecutionEngine
from algo_platform.modules.trading.application.order_service import OrderService
from algo_platform.modules.trading.domain.orders import OrderType, TimeInForce
from algo_platform.modules.trading.infrastructure.brokers.paper import PaperExecutionSimulator
from algo_platform.modules.trading.infrastructure.repositories import (
    SqlOrderRepository,
    SqlPositionRepository,
)
from algo_platform.shared.application.ports import EmailMessage
from algo_platform.shared.domain.types import AccountId, OrderId, Side, TenantId, UserId, utc_now
from algo_platform.shared.infrastructure.encryption import CredentialCipher
from algo_platform.shared.infrastructure.redis_gateway import RedisGateway
from algo_platform.shared.infrastructure.security import hash_password

pytestmark = pytest.mark.e2e


class NullEmail:
    async def send(self, message: EmailMessage) -> None:
        return None


async def _seed_reference(session: AsyncSession) -> uuid.UUID:
    session.add(
        PlanModel(
            id=uuid.uuid4(),
            code="free",
            name="Free",
            description="",
            price_monthly=Decimal("0"),
            price_yearly=Decimal("0"),
            currency="INR",
            features=[],
            limits={
                "max_broker_connections": 1,
                "max_active_strategies": 1,
                "max_orders_per_day": 20,
                "max_members": 1,
                "max_watchlists": 3,
                "api_access": False,
                "live_trading": False,
            },
            trial_days=0,
            is_active=True,
            sort_order=0,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
    )
    session.add(
        BrokerModel(
            id=uuid.uuid4(),
            code="paper",
            name="Paper Trading",
            description="",
            credential_fields=[
                {"name": "starting_balance", "label": "Balance", "secret": False},
                {"name": "base_currency", "label": "Currency", "secret": False},
            ],
            capabilities={},
            supports_paper=True,
            supports_live=False,
            is_active=True,
            created_at=utc_now(),
        )
    )
    instrument_id = uuid.uuid4()
    session.add(
        InstrumentModel(
            id=instrument_id,
            symbol="RELIANCE",
            name="Reliance",
            exchange="NSE",
            asset_class="equity",
            currency="INR",
            tick_size=Decimal("0.05"),
            lot_size=Decimal("1"),
            price_precision=2,
            reference_price=Decimal("2900"),
            is_active=True,
            created_at=utc_now(),
        )
    )
    await session.commit()
    return instrument_id


def _billing(session: AsyncSession) -> SubscriptionService:
    return SubscriptionService(session=session, providers={}, app_base_url="http://x")


async def test_full_paper_slice(
    session_factory: async_sessionmaker[AsyncSession],
    _redis_url: str,
    kek_b64: str,
) -> None:
    redis = RedisGateway.from_url(_redis_url)
    cipher = CredentialCipher.from_base64(kek_b64)

    # -- seed + register + org ------------------------------------------------
    async with session_factory() as session:
        instrument_id = await _seed_reference(session)

    user_id = UserId(uuid.uuid4())
    async with session_factory() as session:
        users = SqlUserRepository(session)
        await users.add(
            User(
                id=user_id,
                email="e2e@example.com",
                full_name="E2E",
                password_hash=hash_password("Str0ngPass99"),
                email_verified_at=utc_now(),
            )
        )
        org_service = OrganizationService(
            organizations=SqlOrganizationRepository(session),
            memberships=SqlMembershipRepository(session),
            invitations=SqlInvitationRepository(session),
            directory=UserDirectory(session),
            email_sender=NullEmail(),
            settings=_settings(kek_b64),
        )
        org = await org_service.create_organization(name="E2E Org", owner_user_id=user_id)
        org_id = org.id
        await session.commit()

    # -- connect paper broker (creates a paper trading account) ---------------
    async with session_factory() as session:
        brokerage = BrokerageService(
            catalog=SqlBrokerCatalogRepository(session),
            connections=SqlBrokerConnectionRepository(session),
            accounts=SqlTradingAccountRepository(session),
            verifiers=build_verifier_registry(),
            cipher=cipher,
            billing=_billing(session),
        )
        connection = await brokerage.add_connection(
            org_id,
            broker_code="paper",
            name="Paper account",
            credentials={"starting_balance": "1000000", "base_currency": "INR"},
            created_by=user_id,
            account_mode="paper",
        )
        await session.commit()
    assert connection.status == "verified"
    account_id = AccountId(uuid.UUID(connection.accounts[0].id))

    # -- place a market buy order --------------------------------------------
    async with session_factory() as session:
        order_service = OrderService(
            session=session,
            redis=redis,
            billing=_billing(session),
            risk=RiskService(session),
        )
        order = await order_service.place_order(
            TenantId(org_id),
            account_id=account_id,
            instrument_id=instrument_id,
            side=Side.BUY,
            quantity=Decimal("10"),
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
            limit_price=None,
            stop_price=None,
            client_order_id="e2e-order-1",
        )
        await session.commit()
    assert order.status.value == "approved"
    order_id = order.id

    # -- idempotency: same client_order_id returns the original order ---------
    async with session_factory() as session:
        order_service = OrderService(
            session=session,
            redis=redis,
            billing=_billing(session),
            risk=RiskService(session),
        )
        duplicate = await order_service.place_order(
            TenantId(org_id),
            account_id=account_id,
            instrument_id=instrument_id,
            side=Side.BUY,
            quantity=Decimal("10"),
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
            limit_price=None,
            stop_price=None,
            client_order_id="e2e-order-1",
        )
        await session.commit()
    assert duplicate.id == order_id  # no second order created

    # -- run the paper engine: submit then feed a tick to fill ----------------
    engine = PaperExecutionEngine(
        session_factory=session_factory,
        redis=redis,
        simulator=PaperExecutionSimulator(seed=1),
    )
    await engine.handle_submit(order_id)
    # Two ticks so a possible partial fill completes.
    for _ in range(3):
        await engine.on_tick(instrument_id, Decimal("2899.5"), Decimal("2900.5"))

    # -- verify order filled, position opened, cash reduced -------------------
    async with session_factory() as session:
        filled = await SqlOrderRepository(session).get_any(OrderId(order_id))
        assert filled is not None
        assert filled.status.value == "filled"
        assert filled.filled_quantity == Decimal("10")

        positions = await SqlPositionRepository(session).list_for_account(account_id)
        assert len(positions) == 1
        assert positions[0].quantity == Decimal("10")
        assert positions[0].average_price > 0

        account = await SqlTradingAccountRepository(session).get(TenantId(org_id), account_id)
        assert account is not None
        assert account.cash_balance < Decimal("1000000")

    await redis.close()


def _settings(kek_b64: str):
    from algo_platform.config import Settings

    return Settings(
        database_url="postgresql+asyncpg://x/y",
        redis_url="redis://x",
        jwt_private_key_pem="x",
        jwt_public_key_pem="x",
        broker_credential_kek_b64=kek_b64,
    )  # type: ignore[call-arg]
