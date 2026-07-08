"""Integration: subscription lifecycle, entitlement enforcement, coupon settle."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from algo_platform.modules.billing.application.ports import CheckoutSession, WebhookResult
from algo_platform.modules.billing.application.service import SubscriptionService
from algo_platform.modules.billing.domain.coupons import Coupon
from algo_platform.modules.billing.domain.plans import BillingCycle
from algo_platform.modules.billing.infrastructure.models import PlanModel
from algo_platform.modules.billing.infrastructure.repositories import SqlCouponRepository
from algo_platform.shared.domain.errors import EntitlementExceeded
from algo_platform.shared.domain.types import TenantId, utc_now

pytestmark = pytest.mark.integration


async def _seed_pro_plan(session: AsyncSession) -> None:
    session.add(
        PlanModel(
            id=uuid.uuid4(),
            code="pro",
            name="Pro",
            description="",
            price_monthly=Decimal("2499"),
            price_yearly=Decimal("24990"),
            currency="INR",
            features=[],
            limits={
                "max_broker_connections": 5,
                "max_active_strategies": 10,
                "max_orders_per_day": 1000,
                "max_members": 10,
                "max_watchlists": 25,
                "api_access": True,
                "live_trading": True,
            },
            provider_prices={"fake:monthly": "fake_price_monthly"},
            trial_days=14,
            is_active=True,
            sort_order=2,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
    )
    await session.commit()


async def test_free_subscription_enforces_limits(
    session_factory: async_sessionmaker[AsyncSession], seeded_plans: None
) -> None:
    org_id = TenantId(uuid.uuid4())
    async with session_factory() as session:
        service = SubscriptionService(session=session, providers={}, app_base_url="http://x")
        # Free plan allows a single broker connection.
        await service.require_within_limit(org_id, metric="max_broker_connections", current=0)
        with pytest.raises(EntitlementExceeded):
            await service.require_within_limit(org_id, metric="max_broker_connections", current=1)
        # Free plan forbids live trading.
        with pytest.raises(EntitlementExceeded):
            await service.require_feature(org_id, feature="live_trading")
        await session.commit()


async def test_fully_discounted_checkout_activates_plan(
    session_factory: async_sessionmaker[AsyncSession], seeded_plans: None
) -> None:
    org_id = TenantId(uuid.uuid4())
    async with session_factory() as session:
        await _seed_pro_plan(session)
        coupon = Coupon.create(
            code="FREEPRO",
            description="100% off",
            percent_off=Decimal("100"),
            amount_off=None,
            currency="INR",
            max_redemptions=None,
            valid_from=None,
            valid_until=None,
            applies_plan_codes=[],
        )
        await SqlCouponRepository(session).add(coupon)
        await session.commit()

    async with session_factory() as session:
        service = SubscriptionService(session=session, providers={}, app_base_url="http://x")
        result = await service.start_checkout(
            org_id,
            plan_code="pro",
            cycle=BillingCycle.MONTHLY,
            provider_name=None,
            coupon_code="FREEPRO",
            customer_email="user@example.com",
        )
        await session.commit()
    assert result.kind == "activated"

    async with session_factory() as session:
        service = SubscriptionService(session=session, providers={}, app_base_url="http://x")
        summary = await service.get_summary(org_id)
        # Now on Pro: live trading and higher limits are available.
        await service.require_feature(org_id, feature="live_trading")
        await session.commit()
    assert summary.plan_code == "pro"
    assert summary.status == "active"


async def test_usage_tracking_accumulates(
    session_factory: async_sessionmaker[AsyncSession], seeded_plans: None
) -> None:
    org_id = TenantId(uuid.uuid4())
    async with session_factory() as session:
        service = SubscriptionService(session=session, providers={}, app_base_url="http://x")
        await service.get_or_create_subscription(org_id)
        for _ in range(3):
            await service.record_usage(org_id, metric="orders_placed")
        await session.commit()
    async with session_factory() as session:
        service = SubscriptionService(session=session, providers={}, app_base_url="http://x")
        placed = await service.orders_placed_today(org_id)
    assert placed == 3


class FakeRecurringProvider:
    name = "fake"

    async def create_checkout(
        self,
        *,
        invoice: Any,
        plan_name: str,
        customer_email: str,
        success_url: str,
        cancel_url: str,
        provider_price_ref: str | None,
        billing_cycle: str,
    ) -> CheckoutSession:
        assert provider_price_ref == "fake_price_monthly"
        return CheckoutSession(
            provider=self.name,
            checkout_id="sub_fake_123",
            checkout_url="https://checkout.example.test/sub_fake_123",
            payload={},
            recurring=True,
        )

    async def cancel_subscription(
        self, provider_subscription_id: str, *, at_period_end: bool
    ) -> None:
        return None

    async def resume_subscription(self, provider_subscription_id: str) -> None:
        return None

    def verify_webhook(
        self, *, body: bytes, headers: Mapping[str, str]
    ) -> WebhookResult:
        raise NotImplementedError


async def test_recurring_checkout_and_webhook_activate_subscription(
    session_factory: async_sessionmaker[AsyncSession],
    seeded_plans: None,
) -> None:
    org_id = TenantId(uuid.uuid4())
    provider = FakeRecurringProvider()
    async with session_factory() as session:
        await _seed_pro_plan(session)
        service = SubscriptionService(
            session=session,
            providers={"fake": provider},
            app_base_url="https://app.example.test",
        )
        checkout = await service.start_checkout(
            org_id,
            plan_code="pro",
            cycle=BillingCycle.MONTHLY,
            provider_name="fake",
            coupon_code=None,
            customer_email="trader@example.com",
        )
        assert checkout.checkout is not None and checkout.checkout.recurring
        assert checkout.invoice_id is not None
        await session.commit()

    async with session_factory() as session:
        service = SubscriptionService(
            session=session,
            providers={"fake": provider},
            app_base_url="https://app.example.test",
        )
        await service.handle_webhook(
            provider_name="fake",
            result=WebhookResult(
                kind="payment_captured",
                event_id="evt_fake_1",
                event_type="subscription.charged",
                payload_hash="a" * 64,
                provider_payment_id="pay_fake_1",
                provider_subscription_id="sub_fake_123",
                invoice_id=checkout.invoice_id,
                amount=Decimal("2499"),
                currency="INR",
            ),
        )
        summary = await service.get_summary(org_id)
        await session.commit()

    assert summary.status == "active"
    assert summary.provider == "fake"
    assert summary.provider_status == "active"
