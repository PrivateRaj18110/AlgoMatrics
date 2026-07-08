"""Subscription lifecycle, checkout, webhook settlement, and entitlements."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.billing.application.ports import (
    CheckoutSession,
    PaymentProvider,
    WebhookResult,
)
from algo_platform.modules.billing.domain.coupons import Coupon
from algo_platform.modules.billing.domain.invoices import Invoice, InvoiceStatus, Payment
from algo_platform.modules.billing.domain.plans import BillingCycle, Plan, PlanCode, PlanLimits
from algo_platform.modules.billing.domain.subscriptions import (
    Subscription,
    SubscriptionStatus,
    period_delta,
)
from algo_platform.modules.billing.infrastructure.models import BillingWebhookEventModel
from algo_platform.modules.billing.infrastructure.repositories import (
    SqlCouponRepository,
    SqlInvoiceRepository,
    SqlPaymentRepository,
    SqlPlanRepository,
    SqlSubscriptionRepository,
    SqlUsageRepository,
)
from algo_platform.modules.notifications.application.service import (
    NotificationService,
    Severity,
)
from algo_platform.shared.domain.errors import (
    ConflictError,
    EntitlementExceeded,
    NotFoundError,
    ValidationFailed,
)
from algo_platform.shared.domain.types import DomainEvent, TenantId, utc_now
from algo_platform.shared.infrastructure.outbox import enqueue_event

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SubscriptionSummaryDTO:
    id: UUID
    status: str
    plan_code: str
    plan_name: str
    billing_cycle: str
    price_monthly: Decimal
    price_yearly: Decimal
    currency: str
    current_period_start: datetime
    current_period_end: datetime
    trial_end: datetime | None
    trial_available: bool
    cancel_at_period_end: bool
    limits: dict[str, Any]
    features: list[str]
    provider: str | None
    provider_status: str | None


@dataclass(frozen=True, slots=True)
class CheckoutResultDTO:
    kind: str  # "checkout" | "activated" | "trial_started" | "scheduled"
    checkout: CheckoutSession | None
    invoice_id: UUID | None
    message: str


@dataclass(frozen=True, slots=True)
class CouponPreviewDTO:
    code: str
    description: str
    discount: Decimal
    subtotal: Decimal
    total: Decimal
    currency: str


class SubscriptionService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        providers: dict[str, PaymentProvider],
        app_base_url: str,
        notifications: NotificationService | None = None,
    ) -> None:
        self._session = session
        self._plans = SqlPlanRepository(session)
        self._subscriptions = SqlSubscriptionRepository(session)
        self._invoices = SqlInvoiceRepository(session)
        self._payments = SqlPaymentRepository(session)
        self._coupons = SqlCouponRepository(session)
        self._usage = SqlUsageRepository(session)
        self._providers = providers
        self._app_base_url = app_base_url
        self._notifications = notifications

    # -- plan catalog -------------------------------------------------------

    async def list_plans(self) -> list[Plan]:
        return await self._plans.list_active()

    async def _free_plan(self) -> Plan:
        plan = await self._plans.get_by_code(PlanCode.FREE.value)
        if plan is None:
            raise NotFoundError("free plan is not seeded; run the seed script")
        return plan

    # -- current subscription --------------------------------------------------

    async def get_or_create_subscription(self, organization_id: TenantId) -> Subscription:
        subscription = await self._subscriptions.get_for_organization(organization_id)
        if subscription is not None:
            return subscription
        free = await self._free_plan()
        subscription = Subscription.start_free(organization_id=organization_id, plan_id=free.id)
        await self._subscriptions.add(subscription)
        return subscription

    async def get_summary(self, organization_id: TenantId) -> SubscriptionSummaryDTO:
        subscription = await self.get_or_create_subscription(organization_id)
        plan = await self._plans.get(subscription.plan_id)
        if plan is None:
            plan = await self._free_plan()
        return SubscriptionSummaryDTO(
            id=subscription.id,
            status=subscription.status.value,
            plan_code=plan.code,
            plan_name=plan.name,
            billing_cycle=subscription.billing_cycle.value,
            price_monthly=plan.price_monthly,
            price_yearly=plan.price_yearly,
            currency=plan.currency,
            current_period_start=subscription.current_period_start,
            current_period_end=subscription.current_period_end,
            trial_end=subscription.trial_end,
            trial_available=not subscription.trial_used,
            cancel_at_period_end=subscription.cancel_at_period_end,
            limits=plan.limits.to_mapping(),
            features=list(plan.features),
            provider=subscription.provider,
            provider_status=subscription.provider_status,
        )

    async def current_limits(self, organization_id: TenantId) -> PlanLimits:
        subscription = await self.get_or_create_subscription(organization_id)
        if not subscription.in_paid_period and subscription.status in {
            SubscriptionStatus.PAST_DUE,
            SubscriptionStatus.EXPIRED,
            SubscriptionStatus.CANCELLED,
        }:
            return (await self._free_plan()).limits
        plan = await self._plans.get(subscription.plan_id)
        if plan is None:
            return (await self._free_plan()).limits
        return plan.limits

    # -- entitlements ----------------------------------------------------------

    async def require_within_limit(
        self, organization_id: TenantId, *, metric: str, current: int
    ) -> None:
        limits = await self.current_limits(organization_id)
        if not limits.allows(metric, current):
            raise EntitlementExceeded(
                f"your plan does not allow more than {getattr(limits, metric)} "
                f"for {metric.replace('_', ' ')}; upgrade to continue",
                details={"metric": metric, "limit": getattr(limits, metric)},
            )

    async def require_feature(self, organization_id: TenantId, *, feature: str) -> None:
        limits = await self.current_limits(organization_id)
        allowed = bool(getattr(limits, feature, False))
        if not allowed:
            raise EntitlementExceeded(
                f"the '{feature}' feature requires a higher plan",
                details={"feature": feature},
            )

    async def record_usage(
        self, organization_id: TenantId, *, metric: str, quantity: int = 1
    ) -> None:
        await self._usage.record(
            organization_id=organization_id,
            metric=metric,
            day=utc_now().date(),
            quantity=quantity,
        )

    async def orders_placed_today(self, organization_id: TenantId) -> int:
        return await self._usage.get_quantity(
            organization_id=organization_id,
            metric="orders_placed",
            day=utc_now().date(),
        )

    async def usage_summary(self, organization_id: TenantId) -> dict[str, int]:
        since = utc_now().date() - timedelta(days=30)
        summary = await self._usage.summary_since(organization_id=organization_id, since=since)
        summary["orders_placed_today"] = await self.orders_placed_today(organization_id)
        return summary

    # -- checkout ----------------------------------------------------------------

    async def preview_coupon(
        self, *, code: str, plan_code: str, cycle: BillingCycle
    ) -> CouponPreviewDTO:
        plan = await self._plans.get_by_code(plan_code)
        if plan is None or not plan.is_active:
            raise NotFoundError("plan not found")
        coupon = await self._coupons.get_by_code(code)
        if coupon is None:
            raise NotFoundError("coupon not found")
        coupon.ensure_redeemable(plan_code=plan.code, currency=plan.currency)
        subtotal = plan.price_for(cycle)
        discount = coupon.discount_for(subtotal)
        return CouponPreviewDTO(
            code=coupon.code,
            description=coupon.description,
            discount=discount,
            subtotal=subtotal,
            total=subtotal - discount,
            currency=plan.currency,
        )

    async def start_checkout(
        self,
        organization_id: TenantId,
        *,
        plan_code: str,
        cycle: BillingCycle,
        provider_name: str | None,
        coupon_code: str | None,
        customer_email: str,
        use_trial: bool = False,
    ) -> CheckoutResultDTO:
        plan = await self._plans.get_by_code(plan_code)
        if plan is None or not plan.is_active:
            raise NotFoundError("plan not found or disabled")
        subscription = await self.get_or_create_subscription(organization_id)
        current_plan = await self._plans.get(subscription.plan_id)

        if (
            current_plan is not None
            and current_plan.id == plan.id
            and (
                subscription.status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING}
                and not subscription.cancel_at_period_end
            )
        ):
            raise ConflictError("this organization is already on the selected plan")

        # Free plan: no payment involved.
        if plan.is_free:
            if (
                current_plan is not None
                and not current_plan.is_free
                and (subscription.in_paid_period)
            ):
                subscription.schedule_plan_change(plan.id)
                subscription.cancel_at_period_end = True
                await self._subscriptions.save(subscription)
                return CheckoutResultDTO(
                    kind="scheduled",
                    checkout=None,
                    invoice_id=None,
                    message="downgrade to Free is scheduled for the end of the period",
                )
            subscription.activate_paid(
                plan_id=plan.id,
                cycle=BillingCycle.MONTHLY,
                provider="none",
                provider_ref=None,
            )
            subscription.current_period_end = utc_now() + timedelta(days=36500)
            await self._subscriptions.save(subscription)
            return CheckoutResultDTO(
                kind="activated",
                checkout=None,
                invoice_id=None,
                message="switched to the Free plan",
            )

        # Trial without payment method.
        if use_trial:
            if plan.trial_days <= 0:
                raise ConflictError("this plan does not offer a trial")
            subscription.start_trial(plan_id=plan.id, trial_days=plan.trial_days, cycle=cycle)
            await self._subscriptions.save(subscription)
            await self._emit_subscription_event(
                organization_id, subscription, "billing.trial_started.v1"
            )
            await self._notify(
                organization_id,
                title=f"{plan.name} trial started",
                body=f"Your {plan.trial_days}-day trial is active.",
                type_="billing",
                severity="success",
            )
            return CheckoutResultDTO(
                kind="trial_started",
                checkout=None,
                invoice_id=None,
                message=f"{plan.trial_days}-day trial activated",
            )

        subtotal = plan.price_for(cycle)
        discount = Decimal("0")
        coupon: Coupon | None = None
        if coupon_code:
            coupon = await self._coupons.get_by_code(coupon_code)
            if coupon is None:
                raise NotFoundError("coupon not found")
            coupon.ensure_redeemable(plan_code=plan.code, currency=plan.currency)
            discount = coupon.discount_for(subtotal)

        period_start = utc_now()
        period_end = period_start + period_delta(cycle)
        invoice = Invoice.issue(
            organization_id=organization_id,
            subscription_id=subscription.id,
            number=await self._invoices.next_number(),
            currency=plan.currency,
            subtotal=subtotal,
            discount=discount,
            line_items=[
                {
                    "description": f"{plan.name} plan ({cycle.value})",
                    "plan_code": plan.code,
                    "cycle": cycle.value,
                    "amount": str(subtotal),
                }
            ],
            period_start=period_start,
            period_end=period_end,
            coupon_code=coupon.code if coupon else None,
        )

        # Fully discounted: settle immediately without a gateway round-trip.
        if invoice.total == 0:
            await self._invoices.add(invoice)
            await self._settle_paid_invoice(
                invoice,
                provider="coupon",
                provider_payment_id=f"coupon:{invoice.number}",
                amount=Decimal("0"),
                currency=plan.currency,
                method="coupon",
            )
            return CheckoutResultDTO(
                kind="activated",
                checkout=None,
                invoice_id=invoice.id,
                message="coupon covered the full amount; plan activated",
            )

        provider = self._resolve_provider(provider_name, plan=plan, cycle=cycle)
        provider_price_ref = plan.provider_price(provider.name, cycle)
        if provider_price_ref is None:
            raise ConflictError(
                "recurring billing is not configured for this plan and provider",
                details={
                    "plan": plan.code,
                    "provider": provider.name,
                    "cycle": cycle.value,
                },
            )
        success_url = f"{self._app_base_url}/subscription?payment=success&invoice={invoice.id}"
        cancel_url = f"{self._app_base_url}/subscription?payment=cancelled"
        checkout = await provider.create_checkout(
            invoice=invoice,
            plan_name=plan.name,
            customer_email=customer_email,
            success_url=success_url,
            cancel_url=cancel_url,
            provider_price_ref=provider_price_ref,
            billing_cycle=cycle.value,
        )
        invoice.attach_provider_order(
            provider=provider.name, provider_order_id=checkout.checkout_id
        )
        await self._invoices.add(invoice)
        subscription.provider = provider.name
        subscription.provider_ref = checkout.checkout_id if checkout.recurring else None
        subscription.provider_price_ref = provider_price_ref
        subscription.provider_status = "pending"
        await self._subscriptions.save(subscription)
        logger.info(
            "billing.checkout_created",
            organization_id=str(organization_id),
            invoice=invoice.number,
            provider=provider.name,
        )
        return CheckoutResultDTO(
            kind="checkout",
            checkout=checkout,
            invoice_id=invoice.id,
            message="complete the payment to activate the plan",
        )

    def _resolve_provider(
        self,
        provider_name: str | None,
        *,
        plan: Plan | None = None,
        cycle: BillingCycle | None = None,
    ) -> PaymentProvider:
        if not self._providers:
            raise ConflictError("no payment provider is configured; contact the platform operator")
        if provider_name is None:
            if plan is not None and cycle is not None:
                for candidate in self._providers.values():
                    if plan.provider_price(candidate.name, cycle):
                        return candidate
            raise ConflictError(
                "no configured payment provider supports this plan and billing cycle"
            )
        provider = self._providers.get(provider_name)
        if provider is None:
            raise ValidationFailed(
                f"unknown payment provider '{provider_name}'",
                details={"available": sorted(self._providers)},
            )
        return provider

    # -- settlement -----------------------------------------------------------------

    async def handle_webhook(self, *, provider_name: str, result: WebhookResult) -> None:
        receipt = await self._begin_webhook_receipt(provider_name, result)
        if receipt is None:
            return
        if result.kind == "ignored":
            receipt.status = "ignored"
            receipt.processed_at = utc_now()
            return
        subscription = None
        if result.provider_subscription_id:
            subscription = await self._subscriptions.get_by_provider_ref(
                provider_name, result.provider_subscription_id
            )

        if result.kind in {"subscription_updated", "subscription_cancelled"}:
            if subscription is None:
                logger.warning(
                    "billing.subscription_webhook_unmatched",
                    provider=provider_name,
                    subscription=result.provider_subscription_id,
                )
                receipt.status = "unmatched"
                receipt.processed_at = utc_now()
                return
            provider_status = result.provider_status or (
                "cancelled" if result.kind == "subscription_cancelled" else "active"
            )
            subscription.sync_provider(
                status=self._map_provider_status(provider_status, result.kind),
                provider_status=provider_status,
                period_start=self._timestamp(result.period_start),
                period_end=self._timestamp(result.period_end),
                provider_ref=result.provider_subscription_id,
                customer_id=result.provider_customer_id,
                price_ref=result.provider_price_ref,
                event_at=utc_now(),
            )
            if result.cancel_at_period_end is not None:
                subscription.cancel_at_period_end = result.cancel_at_period_end
            await self._subscriptions.save(subscription)
            receipt.status = "processed"
            receipt.processed_at = utc_now()
            return

        invoice = None
        if result.invoice_id is not None:
            invoice = await self._invoices.get(result.invoice_id)
        if invoice is None and result.provider_order_id:
            invoice = await self._invoices.get_by_provider_order(result.provider_order_id)
        if invoice is None and subscription is not None:
            invoice = await self._invoices.get_latest_open_for_subscription(subscription.id)
        if invoice is None and subscription is not None:
            invoice = await self._issue_provider_invoice(subscription, provider_name, result)
        if invoice is None:
            logger.warning(
                "billing.webhook_unmatched",
                provider=provider_name,
                order=result.provider_order_id,
            )
            receipt.status = "unmatched"
            receipt.processed_at = utc_now()
            return
        if result.kind == "payment_captured":
            if await self._payments.exists_provider_payment(
                provider_name, result.provider_payment_id
            ):
                receipt.status = "duplicate"
                receipt.processed_at = utc_now()
                return  # webhook retry; already settled
            self._validate_provider_amount(invoice, result)
            await self._settle_paid_invoice(
                invoice,
                provider=provider_name,
                provider_payment_id=result.provider_payment_id,
                amount=result.amount if result.amount is not None else invoice.total,
                currency=result.currency or invoice.currency,
                method=result.method,
                provider_subscription_id=result.provider_subscription_id,
                provider_customer_id=result.provider_customer_id,
                provider_price_ref=result.provider_price_ref,
                period_start=self._timestamp(result.period_start),
                period_end=self._timestamp(result.period_end),
            )
        elif result.kind == "payment_failed":
            invoice.mark_failed()
            await self._invoices.save(invoice)
            await self._payments.add(
                Payment.failed(
                    invoice_id=invoice.id,
                    organization_id=invoice.organization_id,
                    provider=provider_name,
                    provider_payment_id=(
                        result.provider_payment_id
                        or result.event_id
                        or f"failed:{invoice.id}"
                    ),
                    amount=result.amount if result.amount is not None else invoice.total,
                    currency=result.currency or invoice.currency,
                    error=result.error,
                )
            )
            await self._notify(
                invoice.organization_id,
                title="Payment failed",
                body=f"Payment for invoice {invoice.number} failed. Please try again.",
                type_="billing",
                severity="warning",
            )
            if subscription is not None:
                subscription.mark_past_due()
                subscription.provider_status = result.provider_status or "past_due"
                subscription.last_provider_event_at = utc_now()
                await self._subscriptions.save(subscription)
        receipt.status = "processed"
        receipt.processed_at = utc_now()

    async def _begin_webhook_receipt(
        self, provider_name: str, result: WebhookResult
    ) -> BillingWebhookEventModel | None:
        event_id = result.event_id or result.payload_hash
        if not event_id:
            raise ValidationFailed("provider webhook did not include an event identifier")
        existing = await self._session.execute(
            select(BillingWebhookEventModel.id).where(
                BillingWebhookEventModel.provider == provider_name,
                BillingWebhookEventModel.provider_event_id == event_id,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return None
        receipt = BillingWebhookEventModel(
            provider=provider_name,
            provider_event_id=event_id,
            event_type=result.event_type or result.kind,
            payload_hash=result.payload_hash,
            status="processing",
            created_at=utc_now(),
        )
        self._session.add(receipt)
        await self._session.flush()
        return receipt

    async def _issue_provider_invoice(
        self,
        subscription: Subscription,
        provider_name: str,
        result: WebhookResult,
    ) -> Invoice:
        plan = await self._plans.get(subscription.plan_id)
        if plan is None:
            raise NotFoundError("subscription plan no longer exists")
        period_start = self._timestamp(result.period_start) or utc_now()
        period_end = self._timestamp(result.period_end) or (
            period_start + period_delta(subscription.billing_cycle)
        )
        expected = plan.price_for(subscription.billing_cycle)
        invoice = Invoice.issue(
            organization_id=subscription.organization_id,
            subscription_id=subscription.id,
            number=await self._invoices.next_number(),
            currency=plan.currency,
            subtotal=expected,
            discount=Decimal("0"),
            line_items=[
                {
                    "description": (
                        f"{plan.name} recurring renewal ({subscription.billing_cycle.value})"
                    ),
                    "plan_code": plan.code,
                    "cycle": subscription.billing_cycle.value,
                    "amount": str(expected),
                }
            ],
            period_start=period_start,
            period_end=period_end,
            coupon_code=None,
        )
        invoice.attach_provider_order(
            provider=provider_name,
            provider_order_id=(
                result.provider_order_id
                or result.event_id
                or f"renewal:{subscription.id}:{period_start.isoformat()}"
            ),
        )
        await self._invoices.add(invoice)
        return invoice

    @staticmethod
    def _validate_provider_amount(invoice: Invoice, result: WebhookResult) -> None:
        if result.amount is not None and result.amount != invoice.total:
            raise ValidationFailed(
                "provider payment amount does not match invoice",
                details={"expected": str(invoice.total), "received": str(result.amount)},
            )
        if result.currency is not None and result.currency.upper() != invoice.currency.upper():
            raise ValidationFailed(
                "provider payment currency does not match invoice",
                details={"expected": invoice.currency, "received": result.currency},
            )

    @staticmethod
    def _timestamp(value: int | None) -> datetime | None:
        return datetime.fromtimestamp(value, tz=UTC) if value else None

    @staticmethod
    def _map_provider_status(provider_status: str, kind: str) -> SubscriptionStatus:
        normalized = provider_status.lower()
        if kind == "subscription_cancelled" or normalized in {
            "cancelled",
            "canceled",
            "completed",
            "expired",
        }:
            return SubscriptionStatus.CANCELLED
        if normalized in {"past_due", "unpaid", "pending", "halted", "paused"}:
            return SubscriptionStatus.PAST_DUE
        if normalized == "trialing":
            return SubscriptionStatus.TRIALING
        return SubscriptionStatus.ACTIVE

    async def confirm_razorpay_payment(
        self,
        organization_id: TenantId,
        *,
        invoice_id: UUID,
        order_id: str,
        payment_id: str,
        signature_valid: bool,
    ) -> None:
        invoice = await self._invoices.get(invoice_id)
        if invoice is None or invoice.organization_id != organization_id:
            raise NotFoundError("invoice not found")
        if not signature_valid:
            raise ValidationFailed("payment signature verification failed")
        if invoice.provider_order_id != order_id:
            raise ValidationFailed("payment does not match the invoice order")
        if invoice.status is InvoiceStatus.PAID:
            return
        if await self._payments.exists_provider_payment("razorpay", payment_id):
            return
        await self._settle_paid_invoice(
            invoice,
            provider="razorpay",
            provider_payment_id=payment_id,
            amount=invoice.total,
            currency=invoice.currency,
            method="razorpay_checkout",
        )

    async def _settle_paid_invoice(
        self,
        invoice: Invoice,
        *,
        provider: str,
        provider_payment_id: str,
        amount: Decimal,
        currency: str,
        method: str | None,
        provider_subscription_id: str | None = None,
        provider_customer_id: str | None = None,
        provider_price_ref: str | None = None,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> None:
        invoice.mark_paid()
        await self._invoices.save(invoice)
        await self._payments.add(
            Payment.captured(
                invoice_id=invoice.id,
                organization_id=invoice.organization_id,
                provider=provider,
                provider_payment_id=provider_payment_id,
                amount=amount,
                currency=currency,
                method=method,
            )
        )
        subscription = await self._subscriptions.get(invoice.subscription_id)
        if subscription is None:
            raise NotFoundError("subscription for invoice not found")
        line = invoice.line_items[0] if invoice.line_items else {}
        plan_code = str(line.get("plan_code", ""))
        cycle = BillingCycle(str(line.get("cycle", BillingCycle.MONTHLY.value)))
        plan = await self._plans.get_by_code(plan_code) if plan_code else None
        if plan is None:
            raise NotFoundError("plan referenced by invoice no longer exists")
        subscription.activate_paid(
            plan_id=plan.id,
            cycle=cycle,
            provider=provider,
            provider_ref=provider_subscription_id or subscription.provider_ref,
        )
        subscription.sync_provider(
            status=SubscriptionStatus.ACTIVE,
            provider_status="active",
            period_start=period_start,
            period_end=period_end,
            provider_ref=provider_subscription_id,
            customer_id=provider_customer_id,
            price_ref=provider_price_ref or plan.provider_price(provider, cycle),
        )
        await self._subscriptions.save(subscription)
        if invoice.coupon_code:
            coupon = await self._coupons.get_by_code(invoice.coupon_code)
            if coupon is not None:
                coupon.record_redemption()
                await self._coupons.save(coupon)
                await self._coupons.record_redemption(
                    coupon_id=coupon.id,
                    organization_id=invoice.organization_id,
                    invoice_id=invoice.id,
                )
        await self._emit_subscription_event(
            invoice.organization_id, subscription, "billing.subscription_activated.v1"
        )
        await self._notify(
            invoice.organization_id,
            title=f"{plan.name} plan activated",
            body=f"Invoice {invoice.number} was paid. Thank you!",
            type_="billing",
            severity="success",
        )
        logger.info(
            "billing.invoice_settled",
            invoice=invoice.number,
            organization_id=str(invoice.organization_id),
            provider=provider,
        )

    # -- cancel / resume ----------------------------------------------------------

    async def cancel_at_period_end(self, organization_id: TenantId) -> None:
        subscription = await self.get_or_create_subscription(organization_id)
        if subscription.provider and subscription.provider_ref:
            provider = self._providers.get(subscription.provider)
            if provider is None:
                raise ConflictError(
                    "subscription provider is unavailable; contact platform support"
                )
            await provider.cancel_subscription(subscription.provider_ref, at_period_end=True)
        subscription.request_cancellation()
        await self._subscriptions.save(subscription)
        await self._notify(
            organization_id,
            title="Subscription cancellation scheduled",
            body="Your plan stays active until the end of the current period.",
            type_="billing",
            severity="info",
        )

    async def resume(self, organization_id: TenantId) -> None:
        subscription = await self.get_or_create_subscription(organization_id)
        if subscription.provider and subscription.provider_ref:
            provider = self._providers.get(subscription.provider)
            if provider is None:
                raise ConflictError(
                    "subscription provider is unavailable; contact platform support"
                )
            await provider.resume_subscription(subscription.provider_ref)
        subscription.resume()
        await self._subscriptions.save(subscription)

    # -- invoices / payments -------------------------------------------------------

    async def list_invoices(
        self, organization_id: TenantId, *, limit: int, offset: int
    ) -> list[Invoice]:
        return await self._invoices.list_for_organization(
            organization_id, limit=limit, offset=offset
        )

    async def get_invoice(self, organization_id: TenantId, invoice_id: UUID) -> Invoice:
        invoice = await self._invoices.get(invoice_id)
        if invoice is None or invoice.organization_id != organization_id:
            raise NotFoundError("invoice not found")
        return invoice

    async def list_payments(
        self, organization_id: TenantId, *, limit: int, offset: int
    ) -> list[Payment]:
        return await self._payments.list_for_organization(
            organization_id, limit=limit, offset=offset
        )

    # -- admin ------------------------------------------------------------------------

    async def grant_manual_subscription(
        self,
        organization_id: TenantId,
        *,
        plan_code: str,
        days: int,
        note: str,
    ) -> None:
        if days < 1 or days > 3650:
            raise ValidationFailed("grant duration must be between 1 and 3650 days")
        plan = await self._plans.get_by_code(plan_code)
        if plan is None:
            raise NotFoundError("plan not found")
        subscription = await self.get_or_create_subscription(organization_id)
        now = utc_now()
        subscription.plan_id = plan.id
        subscription.status = SubscriptionStatus.ACTIVE
        subscription.current_period_start = now
        subscription.current_period_end = now + timedelta(days=days)
        subscription.cancel_at_period_end = False
        subscription.pending_plan_id = None
        subscription.provider = "manual"
        subscription.provider_ref = note[:120] if note else "manual-grant"
        subscription.touch()
        await self._subscriptions.save(subscription)
        invoice = Invoice.issue(
            organization_id=organization_id,
            subscription_id=subscription.id,
            number=await self._invoices.next_number(),
            currency=plan.currency,
            subtotal=Decimal("0"),
            discount=Decimal("0"),
            line_items=[
                {
                    "description": f"Manual grant: {plan.name} for {days} days",
                    "plan_code": plan.code,
                    "cycle": BillingCycle.MONTHLY.value,
                    "note": note,
                }
            ],
            period_start=now,
            period_end=subscription.current_period_end,
            coupon_code=None,
        )
        invoice.mark_paid()
        await self._invoices.add(invoice)
        await self._notify(
            organization_id,
            title=f"{plan.name} plan granted",
            body=f"An administrator granted {plan.name} for {days} days.",
            type_="billing",
            severity="success",
        )

    # -- lifecycle (scheduler) ----------------------------------------------------------

    async def run_lifecycle_tick(self) -> int:
        """Apply rollovers for subscriptions whose period ended. Returns count."""
        free = await self._free_plan()
        due = await self._subscriptions.list_due_for_rollover()
        for subscription in due:
            before_status = subscription.status
            subscription.apply_period_rollover(fallback_plan_id=free.id)
            await self._subscriptions.save(subscription)
            if before_status != subscription.status or subscription.plan_id == free.id:
                await self._notify(
                    subscription.organization_id,
                    title="Subscription updated",
                    body="Your subscription period ended and the plan was adjusted.",
                    type_="billing",
                    severity="info",
                )
        return len(due)

    # -- helpers ---------------------------------------------------------------------------

    async def _emit_subscription_event(
        self, organization_id: TenantId, subscription: Subscription, event_type: str
    ) -> None:
        await enqueue_event(
            self._session,
            event=DomainEvent.new(
                event_type=event_type,
                aggregate_id=subscription.id,
                tenant_id=organization_id,
            ),
            aggregate_type="subscription",
            payload={
                "subscription_id": str(subscription.id),
                "plan_id": str(subscription.plan_id),
                "status": subscription.status.value,
            },
        )

    async def _notify(
        self,
        organization_id: TenantId,
        *,
        title: str,
        body: str,
        type_: str,
        severity: Severity,
    ) -> None:
        if self._notifications is None:
            return
        await self._notifications.notify(
            organization_id=organization_id,
            title=title,
            body=body,
            type_=type_,
            severity=severity,
        )
