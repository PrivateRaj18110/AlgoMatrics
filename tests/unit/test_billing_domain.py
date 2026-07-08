from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from algo_platform.modules.billing.domain.coupons import Coupon
from algo_platform.modules.billing.domain.invoices import Invoice, InvoiceStatus
from algo_platform.modules.billing.domain.plans import (
    BillingCycle,
    Plan,
    PlanLimits,
    normalize_provider_prices,
)
from algo_platform.modules.billing.domain.subscriptions import (
    Subscription,
    SubscriptionStatus,
)
from algo_platform.shared.domain.errors import ConflictError, ValidationFailed
from algo_platform.shared.domain.types import TenantId, utc_now


def make_plan(**overrides: object) -> Plan:
    defaults: dict[str, object] = {
        "code": "pro",
        "name": "Pro",
        "description": "",
        "price_monthly": Decimal("2499"),
        "price_yearly": Decimal("24990"),
        "currency": "INR",
        "features": [],
        "limits": PlanLimits.from_mapping({}),
        "trial_days": 14,
    }
    defaults.update(overrides)
    return Plan.create(**defaults)  # type: ignore[arg-type]


def make_coupon(**overrides: object) -> Coupon:
    defaults: dict[str, object] = {
        "code": "LAUNCH50",
        "description": "50% off",
        "percent_off": Decimal("50"),
        "amount_off": None,
        "currency": "INR",
        "max_redemptions": 10,
        "valid_from": None,
        "valid_until": None,
        "applies_plan_codes": [],
    }
    defaults.update(overrides)
    return Coupon.create(**defaults)  # type: ignore[arg-type]


class TestPlanLimits:
    def test_unlimited_is_negative_one(self) -> None:
        limits = PlanLimits.from_mapping({"max_broker_connections": -1})
        assert limits.allows("max_broker_connections", 10_000)

    def test_limit_blocks_at_threshold(self) -> None:
        limits = PlanLimits.from_mapping({"max_active_strategies": 3})
        assert limits.allows("max_active_strategies", 2)
        assert not limits.allows("max_active_strategies", 3)

    def test_price_for_cycle(self) -> None:
        plan = make_plan()
        assert plan.price_for(BillingCycle.MONTHLY) == Decimal("2499")
        assert plan.price_for(BillingCycle.YEARLY) == Decimal("24990")

    def test_provider_price_references_are_validated(self) -> None:
        assert normalize_provider_prices(
            {
                "stripe:monthly": " price_monthly ",
                "razorpay:yearly": "plan_yearly",
            }
        ) == {
            "stripe:monthly": "price_monthly",
            "razorpay:yearly": "plan_yearly",
        }
        with pytest.raises(ValidationFailed, match="price_"):
            normalize_provider_prices({"stripe:monthly": "plan_wrong"})


class TestCoupon:
    def test_percent_discount(self) -> None:
        coupon = make_coupon()
        assert coupon.discount_for(Decimal("1000")) == Decimal("500.00")

    def test_amount_discount_capped_at_amount(self) -> None:
        coupon = make_coupon(percent_off=None, amount_off=Decimal("300"))
        assert coupon.discount_for(Decimal("1000")) == Decimal("300")
        assert coupon.discount_for(Decimal("200")) == Decimal("200")

    def test_requires_exactly_one_discount_kind(self) -> None:
        with pytest.raises(ValidationFailed):
            make_coupon(percent_off=None, amount_off=None)
        with pytest.raises(ValidationFailed):
            make_coupon(percent_off=Decimal("10"), amount_off=Decimal("10"))

    def test_expiry_window_enforced(self) -> None:
        coupon = make_coupon(valid_until=utc_now() - timedelta(days=1))
        with pytest.raises(ConflictError, match="expired"):
            coupon.ensure_redeemable(plan_code="pro", currency="INR")

    def test_plan_restriction(self) -> None:
        coupon = make_coupon(applies_plan_codes=["starter"])
        with pytest.raises(ConflictError, match="does not apply"):
            coupon.ensure_redeemable(plan_code="pro", currency="INR")
        coupon.ensure_redeemable(plan_code="starter", currency="INR")

    def test_redemption_limit(self) -> None:
        coupon = make_coupon(max_redemptions=1)
        coupon.record_redemption()
        with pytest.raises(ConflictError, match="limit reached"):
            coupon.record_redemption()


class TestSubscription:
    def test_trial_only_once(self) -> None:
        subscription = Subscription.start_free(organization_id=TenantId(uuid4()), plan_id=uuid4())
        subscription.start_trial(plan_id=uuid4(), trial_days=14, cycle=BillingCycle.MONTHLY)
        assert subscription.status is SubscriptionStatus.TRIALING
        assert subscription.trial_used
        with pytest.raises(ConflictError, match="trial already used"):
            subscription.start_trial(plan_id=uuid4(), trial_days=14, cycle=BillingCycle.MONTHLY)

    def test_cancel_and_resume(self) -> None:
        subscription = Subscription.start_free(organization_id=TenantId(uuid4()), plan_id=uuid4())
        subscription.request_cancellation()
        assert subscription.cancel_at_period_end
        subscription.resume()
        assert not subscription.cancel_at_period_end

    def test_expired_trial_falls_back_to_free(self) -> None:
        free_plan_id = uuid4()
        subscription = Subscription.start_free(
            organization_id=TenantId(uuid4()), plan_id=free_plan_id
        )
        subscription.start_trial(plan_id=uuid4(), trial_days=14, cycle=BillingCycle.MONTHLY)
        subscription.current_period_end = utc_now() - timedelta(seconds=1)
        subscription.apply_period_rollover(fallback_plan_id=free_plan_id)
        assert subscription.plan_id == free_plan_id
        assert subscription.status is SubscriptionStatus.ACTIVE

    def test_unpaid_renewal_goes_past_due(self) -> None:
        subscription = Subscription.start_free(organization_id=TenantId(uuid4()), plan_id=uuid4())
        subscription.activate_paid(
            plan_id=uuid4(),
            cycle=BillingCycle.MONTHLY,
            provider="stripe",
            provider_ref="pi_1",
        )
        subscription.current_period_end = utc_now() - timedelta(seconds=1)
        subscription.apply_period_rollover(fallback_plan_id=uuid4())
        assert subscription.status is SubscriptionStatus.PAST_DUE


class TestInvoice:
    def make_invoice(self, subtotal: str, discount: str) -> Invoice:
        now = utc_now()
        return Invoice.issue(
            organization_id=TenantId(uuid4()),
            subscription_id=uuid4(),
            number="INV-2026-000001",
            currency="INR",
            subtotal=Decimal(subtotal),
            discount=Decimal(discount),
            line_items=[],
            period_start=now,
            period_end=now + timedelta(days=30),
            coupon_code=None,
        )

    def test_total_never_negative(self) -> None:
        invoice = self.make_invoice("100", "150")
        assert invoice.total == Decimal("0")

    def test_mark_paid_once(self) -> None:
        invoice = self.make_invoice("100", "0")
        invoice.mark_paid()
        assert invoice.status is InvoiceStatus.PAID
        with pytest.raises(ConflictError):
            invoice.mark_paid()

    def test_cannot_void_paid(self) -> None:
        invoice = self.make_invoice("100", "0")
        invoice.mark_paid()
        with pytest.raises(ConflictError):
            invoice.void()
