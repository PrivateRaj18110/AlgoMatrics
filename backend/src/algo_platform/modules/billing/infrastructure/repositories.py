from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.billing.domain.coupons import Coupon
from algo_platform.modules.billing.domain.invoices import (
    Invoice,
    InvoiceStatus,
    Payment,
    PaymentStatus,
)
from algo_platform.modules.billing.domain.plans import BillingCycle, Plan, PlanLimits
from algo_platform.modules.billing.domain.subscriptions import (
    Subscription,
    SubscriptionStatus,
)
from algo_platform.modules.billing.infrastructure.models import (
    CouponModel,
    CouponRedemptionModel,
    InvoiceModel,
    PaymentModel,
    PlanModel,
    SubscriptionModel,
    UsageRecordModel,
)
from algo_platform.shared.domain.types import TenantId, utc_now


def _plan_to_entity(model: PlanModel) -> Plan:
    return Plan(
        id=model.id,
        code=model.code,
        name=model.name,
        description=model.description,
        price_monthly=model.price_monthly,
        price_yearly=model.price_yearly,
        currency=model.currency,
        features=list(model.features),
        limits=PlanLimits.from_mapping(dict(model.limits)),
        provider_prices=dict(model.provider_prices),
        trial_days=model.trial_days,
        is_active=model.is_active,
        sort_order=model.sort_order,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlPlanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, plan: Plan) -> None:
        self._session.add(
            PlanModel(
                id=plan.id,
                code=plan.code,
                name=plan.name,
                description=plan.description,
                price_monthly=plan.price_monthly,
                price_yearly=plan.price_yearly,
                currency=plan.currency,
                features=list(plan.features),
                limits=plan.limits.to_mapping(),
                provider_prices=dict(plan.provider_prices),
                trial_days=plan.trial_days,
                is_active=plan.is_active,
                sort_order=plan.sort_order,
                created_at=plan.created_at,
                updated_at=plan.updated_at,
            )
        )
        await self._session.flush()

    async def get(self, plan_id: UUID) -> Plan | None:
        model = await self._session.get(PlanModel, plan_id)
        return _plan_to_entity(model) if model else None

    async def get_by_code(self, code: str) -> Plan | None:
        result = await self._session.execute(
            select(PlanModel).where(PlanModel.code == code.strip().lower())
        )
        model = result.scalar_one_or_none()
        return _plan_to_entity(model) if model else None

    async def list_active(self) -> list[Plan]:
        result = await self._session.execute(
            select(PlanModel).where(PlanModel.is_active).order_by(PlanModel.sort_order)
        )
        return [_plan_to_entity(m) for m in result.scalars().all()]

    async def list_all(self) -> list[Plan]:
        result = await self._session.execute(select(PlanModel).order_by(PlanModel.sort_order))
        return [_plan_to_entity(m) for m in result.scalars().all()]

    async def save(self, plan: Plan) -> None:
        model = await self._session.get(PlanModel, plan.id)
        if model is None:
            raise LookupError(f"plan {plan.id} not found")
        model.name = plan.name
        model.description = plan.description
        model.price_monthly = plan.price_monthly
        model.price_yearly = plan.price_yearly
        model.currency = plan.currency
        model.features = list(plan.features)
        model.limits = plan.limits.to_mapping()
        model.provider_prices = dict(plan.provider_prices)
        model.trial_days = plan.trial_days
        model.is_active = plan.is_active
        model.sort_order = plan.sort_order
        model.updated_at = utc_now()
        await self._session.flush()


def _subscription_to_entity(model: SubscriptionModel) -> Subscription:
    return Subscription(
        id=model.id,
        organization_id=TenantId(model.organization_id),
        plan_id=model.plan_id,
        status=SubscriptionStatus(model.status),
        billing_cycle=BillingCycle(model.billing_cycle),
        current_period_start=model.current_period_start,
        current_period_end=model.current_period_end,
        trial_end=model.trial_end,
        trial_used=model.trial_used,
        cancel_at_period_end=model.cancel_at_period_end,
        pending_plan_id=model.pending_plan_id,
        provider=model.provider,
        provider_ref=model.provider_ref,
        provider_customer_id=model.provider_customer_id,
        provider_price_ref=model.provider_price_ref,
        provider_status=model.provider_status,
        last_provider_event_at=model.last_provider_event_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
        version=model.version,
    )


class SqlSubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, subscription: Subscription) -> None:
        self._session.add(
            SubscriptionModel(
                id=subscription.id,
                organization_id=subscription.organization_id,
                plan_id=subscription.plan_id,
                status=subscription.status.value,
                billing_cycle=subscription.billing_cycle.value,
                current_period_start=subscription.current_period_start,
                current_period_end=subscription.current_period_end,
                trial_end=subscription.trial_end,
                trial_used=subscription.trial_used,
                cancel_at_period_end=subscription.cancel_at_period_end,
                pending_plan_id=subscription.pending_plan_id,
                provider=subscription.provider,
                provider_ref=subscription.provider_ref,
                provider_customer_id=subscription.provider_customer_id,
                provider_price_ref=subscription.provider_price_ref,
                provider_status=subscription.provider_status,
                last_provider_event_at=subscription.last_provider_event_at,
                created_at=subscription.created_at,
                updated_at=subscription.updated_at,
                version=subscription.version,
            )
        )
        await self._session.flush()

    async def get_for_organization(self, organization_id: TenantId) -> Subscription | None:
        result = await self._session.execute(
            select(SubscriptionModel).where(SubscriptionModel.organization_id == organization_id)
        )
        model = result.scalar_one_or_none()
        return _subscription_to_entity(model) if model else None

    async def get(self, subscription_id: UUID) -> Subscription | None:
        model = await self._session.get(SubscriptionModel, subscription_id)
        return _subscription_to_entity(model) if model else None

    async def get_by_provider_ref(
        self, provider: str, provider_ref: str
    ) -> Subscription | None:
        result = await self._session.execute(
            select(SubscriptionModel).where(
                SubscriptionModel.provider == provider,
                SubscriptionModel.provider_ref == provider_ref,
            )
        )
        model = result.scalar_one_or_none()
        return _subscription_to_entity(model) if model else None

    async def save(self, subscription: Subscription) -> None:
        model = await self._session.get(SubscriptionModel, subscription.id)
        if model is None:
            raise LookupError(f"subscription {subscription.id} not found")
        model.plan_id = subscription.plan_id
        model.status = subscription.status.value
        model.billing_cycle = subscription.billing_cycle.value
        model.current_period_start = subscription.current_period_start
        model.current_period_end = subscription.current_period_end
        model.trial_end = subscription.trial_end
        model.trial_used = subscription.trial_used
        model.cancel_at_period_end = subscription.cancel_at_period_end
        model.pending_plan_id = subscription.pending_plan_id
        model.provider = subscription.provider
        model.provider_ref = subscription.provider_ref
        model.provider_customer_id = subscription.provider_customer_id
        model.provider_price_ref = subscription.provider_price_ref
        model.provider_status = subscription.provider_status
        model.last_provider_event_at = subscription.last_provider_event_at
        model.updated_at = utc_now()
        model.version = subscription.version + 1
        await self._session.flush()

    async def list_due_for_rollover(self, *, limit: int = 200) -> list[Subscription]:
        result = await self._session.execute(
            select(SubscriptionModel)
            .where(
                SubscriptionModel.current_period_end <= utc_now(),
                SubscriptionModel.status.in_(
                    [
                        SubscriptionStatus.ACTIVE.value,
                        SubscriptionStatus.TRIALING.value,
                        SubscriptionStatus.PAST_DUE.value,
                    ]
                ),
            )
            .limit(limit)
        )
        return [_subscription_to_entity(m) for m in result.scalars().all()]


def _invoice_to_entity(model: InvoiceModel) -> Invoice:
    return Invoice(
        id=model.id,
        organization_id=TenantId(model.organization_id),
        subscription_id=model.subscription_id,
        number=model.number,
        status=InvoiceStatus(model.status),
        currency=model.currency,
        subtotal=model.subtotal,
        discount=model.discount,
        tax=model.tax,
        tax_rate=model.tax_rate,
        total=model.total,
        line_items=[dict(item) for item in model.line_items],
        period_start=model.period_start,
        period_end=model.period_end,
        coupon_code=model.coupon_code,
        provider=model.provider,
        provider_order_id=model.provider_order_id,
        issued_at=model.issued_at,
        paid_at=model.paid_at,
        created_at=model.created_at,
    )


class SqlInvoiceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def next_number(self) -> str:
        value = (
            await self._session.execute(text("SELECT nextval('invoice_number_seq')"))
        ).scalar_one()
        return f"INV-{utc_now():%Y}-{int(value):06d}"

    async def add(self, invoice: Invoice) -> None:
        self._session.add(
            InvoiceModel(
                id=invoice.id,
                organization_id=invoice.organization_id,
                subscription_id=invoice.subscription_id,
                number=invoice.number,
                status=invoice.status.value,
                currency=invoice.currency,
                subtotal=invoice.subtotal,
                discount=invoice.discount,
                tax=invoice.tax,
                tax_rate=invoice.tax_rate,
                total=invoice.total,
                line_items=list(invoice.line_items),
                period_start=invoice.period_start,
                period_end=invoice.period_end,
                coupon_code=invoice.coupon_code,
                provider=invoice.provider,
                provider_order_id=invoice.provider_order_id,
                issued_at=invoice.issued_at,
                paid_at=invoice.paid_at,
                created_at=invoice.created_at,
            )
        )
        await self._session.flush()

    async def get(self, invoice_id: UUID) -> Invoice | None:
        model = await self._session.get(InvoiceModel, invoice_id)
        return _invoice_to_entity(model) if model else None

    async def get_by_provider_order(self, provider_order_id: str) -> Invoice | None:
        result = await self._session.execute(
            select(InvoiceModel).where(InvoiceModel.provider_order_id == provider_order_id)
        )
        model = result.scalars().first()
        return _invoice_to_entity(model) if model else None

    async def get_latest_open_for_subscription(
        self, subscription_id: UUID
    ) -> Invoice | None:
        result = await self._session.execute(
            select(InvoiceModel)
            .where(
                InvoiceModel.subscription_id == subscription_id,
                InvoiceModel.status == InvoiceStatus.OPEN.value,
            )
            .order_by(InvoiceModel.issued_at.desc())
            .limit(1)
        )
        model = result.scalar_one_or_none()
        return _invoice_to_entity(model) if model else None

    async def list_for_organization(
        self, organization_id: TenantId, *, limit: int, offset: int
    ) -> list[Invoice]:
        result = await self._session.execute(
            select(InvoiceModel)
            .where(InvoiceModel.organization_id == organization_id)
            .order_by(InvoiceModel.issued_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [_invoice_to_entity(m) for m in result.scalars().all()]

    async def save(self, invoice: Invoice) -> None:
        model = await self._session.get(InvoiceModel, invoice.id)
        if model is None:
            raise LookupError(f"invoice {invoice.id} not found")
        model.status = invoice.status.value
        model.provider = invoice.provider
        model.provider_order_id = invoice.provider_order_id
        model.paid_at = invoice.paid_at
        await self._session.flush()


class SqlPaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, payment: Payment) -> None:
        self._session.add(
            PaymentModel(
                id=payment.id,
                invoice_id=payment.invoice_id,
                organization_id=payment.organization_id,
                provider=payment.provider,
                provider_payment_id=payment.provider_payment_id,
                amount=payment.amount,
                currency=payment.currency,
                status=payment.status.value,
                method=payment.method,
                error=payment.error,
                captured_at=payment.captured_at,
                created_at=payment.created_at,
            )
        )
        await self._session.flush()

    async def exists_provider_payment(self, provider: str, provider_payment_id: str) -> bool:
        result = await self._session.execute(
            select(func.count())
            .select_from(PaymentModel)
            .where(
                PaymentModel.provider == provider,
                PaymentModel.provider_payment_id == provider_payment_id,
            )
        )
        return int(result.scalar_one()) > 0

    async def list_for_organization(
        self, organization_id: TenantId, *, limit: int, offset: int
    ) -> list[Payment]:
        result = await self._session.execute(
            select(PaymentModel)
            .where(PaymentModel.organization_id == organization_id)
            .order_by(PaymentModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [
            Payment(
                id=m.id,
                invoice_id=m.invoice_id,
                organization_id=TenantId(m.organization_id),
                provider=m.provider,
                provider_payment_id=m.provider_payment_id,
                amount=m.amount,
                currency=m.currency,
                status=PaymentStatus(m.status),
                method=m.method,
                error=m.error,
                captured_at=m.captured_at,
                created_at=m.created_at,
            )
            for m in result.scalars().all()
        ]


def _coupon_to_entity(model: CouponModel) -> Coupon:
    return Coupon(
        id=model.id,
        code=model.code,
        description=model.description,
        percent_off=model.percent_off,
        amount_off=model.amount_off,
        currency=model.currency,
        max_redemptions=model.max_redemptions,
        redeemed_count=model.redeemed_count,
        valid_from=model.valid_from,
        valid_until=model.valid_until,
        is_active=model.is_active,
        applies_plan_codes=list(model.applies_plan_codes),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class SqlCouponRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, coupon: Coupon) -> None:
        self._session.add(
            CouponModel(
                id=coupon.id,
                code=coupon.code,
                description=coupon.description,
                percent_off=coupon.percent_off,
                amount_off=coupon.amount_off,
                currency=coupon.currency,
                max_redemptions=coupon.max_redemptions,
                redeemed_count=coupon.redeemed_count,
                valid_from=coupon.valid_from,
                valid_until=coupon.valid_until,
                is_active=coupon.is_active,
                applies_plan_codes=list(coupon.applies_plan_codes),
                created_at=coupon.created_at,
                updated_at=coupon.updated_at,
            )
        )
        await self._session.flush()

    async def get(self, coupon_id: UUID) -> Coupon | None:
        model = await self._session.get(CouponModel, coupon_id)
        return _coupon_to_entity(model) if model else None

    async def get_by_code(self, code: str) -> Coupon | None:
        result = await self._session.execute(
            select(CouponModel).where(CouponModel.code == code.strip().upper())
        )
        model = result.scalar_one_or_none()
        return _coupon_to_entity(model) if model else None

    async def list_all(self) -> list[Coupon]:
        result = await self._session.execute(
            select(CouponModel).order_by(CouponModel.created_at.desc())
        )
        return [_coupon_to_entity(m) for m in result.scalars().all()]

    async def save(self, coupon: Coupon) -> None:
        model = await self._session.get(CouponModel, coupon.id)
        if model is None:
            raise LookupError(f"coupon {coupon.id} not found")
        model.description = coupon.description
        model.max_redemptions = coupon.max_redemptions
        model.redeemed_count = coupon.redeemed_count
        model.valid_from = coupon.valid_from
        model.valid_until = coupon.valid_until
        model.is_active = coupon.is_active
        model.applies_plan_codes = list(coupon.applies_plan_codes)
        model.updated_at = utc_now()
        await self._session.flush()

    async def record_redemption(
        self, *, coupon_id: UUID, organization_id: TenantId, invoice_id: UUID
    ) -> None:
        self._session.add(
            CouponRedemptionModel(
                coupon_id=coupon_id,
                organization_id=organization_id,
                invoice_id=invoice_id,
                redeemed_at=utc_now(),
            )
        )
        await self._session.flush()


class SqlUsageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self, *, organization_id: TenantId, metric: str, day: date, quantity: int = 1
    ) -> None:
        stmt = pg_insert(UsageRecordModel).values(
            organization_id=organization_id,
            metric=metric,
            day=day,
            quantity=quantity,
            updated_at=utc_now(),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["organization_id", "metric", "day"],
            set_={
                "quantity": UsageRecordModel.quantity + quantity,
                "updated_at": utc_now(),
            },
        )
        await self._session.execute(stmt)

    async def get_quantity(self, *, organization_id: TenantId, metric: str, day: date) -> int:
        result = await self._session.execute(
            select(UsageRecordModel.quantity).where(
                UsageRecordModel.organization_id == organization_id,
                UsageRecordModel.metric == metric,
                UsageRecordModel.day == day,
            )
        )
        value = result.scalar_one_or_none()
        return int(value or 0)

    async def summary_since(self, *, organization_id: TenantId, since: date) -> dict[str, int]:
        result = await self._session.execute(
            select(UsageRecordModel.metric, func.sum(UsageRecordModel.quantity))
            .where(
                UsageRecordModel.organization_id == organization_id,
                UsageRecordModel.day >= since,
            )
            .group_by(UsageRecordModel.metric)
        )
        summary: dict[str, int] = {}
        for metric, total in result.tuples().all():
            summary[str(metric)] = int(total or 0)
        return summary


__all__ = [
    "SqlCouponRepository",
    "SqlInvoiceRepository",
    "SqlPaymentRepository",
    "SqlPlanRepository",
    "SqlSubscriptionRepository",
    "SqlUsageRepository",
]
