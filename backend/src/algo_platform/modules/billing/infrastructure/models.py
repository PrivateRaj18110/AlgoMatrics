from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from algo_platform.shared.infrastructure.database import Base


class PlanModel(Base):
    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(500), default="")
    price_monthly: Mapped[Decimal]
    price_yearly: Mapped[Decimal]
    currency: Mapped[str] = mapped_column(String(3))
    features: Mapped[list[str]] = mapped_column(default=list)
    limits: Mapped[dict[str, Any]] = mapped_column(default=dict)
    provider_prices: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict)
    trial_days: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SubscriptionModel(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        Index("ix_subscriptions_org", "organization_id", unique=True),
        Index(
            "ix_subscriptions_provider_ref",
            "provider",
            "provider_ref",
            unique=True,
            postgresql_where=text("provider_ref IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plans.id"))
    status: Mapped[str] = mapped_column(String(20))
    billing_cycle: Mapped[str] = mapped_column(String(10), default="monthly")
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    trial_end: Mapped[datetime | None] = mapped_column(default=None)
    trial_used: Mapped[bool] = mapped_column(Boolean, default=False)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    pending_plan_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    provider: Mapped[str | None] = mapped_column(String(20), default=None)
    provider_ref: Mapped[str | None] = mapped_column(String(120), default=None)
    provider_customer_id: Mapped[str | None] = mapped_column(String(120), default=None)
    provider_price_ref: Mapped[str | None] = mapped_column(String(120), default=None)
    provider_status: Mapped[str | None] = mapped_column(String(30), default=None)
    last_provider_event_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(BigInteger, default=1)


class InvoiceModel(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        Index("ix_invoices_org_time", "organization_id", "issued_at"),
        Index("ix_invoices_provider_order", "provider_order_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("subscriptions.id"))
    number: Mapped[str] = mapped_column(String(40), unique=True)
    status: Mapped[str] = mapped_column(String(15))
    currency: Mapped[str] = mapped_column(String(3))
    subtotal: Mapped[Decimal]
    discount: Mapped[Decimal]
    tax: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    tax_rate: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    total: Mapped[Decimal]
    line_items: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    coupon_code: Mapped[str | None] = mapped_column(String(40), default=None)
    provider: Mapped[str | None] = mapped_column(String(20), default=None)
    provider_order_id: Mapped[str | None] = mapped_column(String(120), default=None)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PaymentModel(Base):
    __tablename__ = "payments"
    __table_args__ = (
        Index("ix_payments_org_time", "organization_id", "created_at"),
        UniqueConstraint("provider", "provider_payment_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id"))
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    provider: Mapped[str] = mapped_column(String(20))
    provider_payment_id: Mapped[str] = mapped_column(String(120))
    amount: Mapped[Decimal]
    refunded_amount: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(15))
    method: Mapped[str | None] = mapped_column(String(30), default=None)
    error: Mapped[str | None] = mapped_column(String(300), default=None)
    captured_at: Mapped[datetime | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CouponModel(Base):
    __tablename__ = "coupons"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    description: Mapped[str] = mapped_column(String(300), default="")
    percent_off: Mapped[Decimal | None] = mapped_column(default=None)
    amount_off: Mapped[Decimal | None] = mapped_column(default=None)
    currency: Mapped[str] = mapped_column(String(3))
    max_redemptions: Mapped[int | None] = mapped_column(default=None)
    redeemed_count: Mapped[int] = mapped_column(default=0)
    valid_from: Mapped[datetime | None] = mapped_column(default=None)
    valid_until: Mapped[datetime | None] = mapped_column(default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    applies_plan_codes: Mapped[list[str]] = mapped_column(default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CouponRedemptionModel(Base):
    __tablename__ = "coupon_redemptions"
    __table_args__ = (UniqueConstraint("coupon_id", "invoice_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    coupon_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("coupons.id"))
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id"))
    redeemed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UsageRecordModel(Base):
    __tablename__ = "usage_records"
    __table_args__ = (UniqueConstraint("organization_id", "metric", "day"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    metric: Mapped[str] = mapped_column(String(50))
    day: Mapped[date] = mapped_column(Date)
    quantity: Mapped[int] = mapped_column(BigInteger, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BillingWebhookEventModel(Base):
    """Immutable provider webhook receipt for replay protection and support."""

    __tablename__ = "billing_webhook_events"
    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id"),
        Index("ix_billing_webhook_events_created", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(20))
    provider_event_id: Mapped[str] = mapped_column(String(160))
    event_type: Mapped[str] = mapped_column(String(80))
    payload_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="processing")
    error: Mapped[str | None] = mapped_column(String(500), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(default=None)
