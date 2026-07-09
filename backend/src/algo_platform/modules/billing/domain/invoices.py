from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from algo_platform.modules.billing.domain.tax import compute_tax
from algo_platform.shared.domain.errors import ConflictError
from algo_platform.shared.domain.types import TenantId, utc_now


class InvoiceStatus(StrEnum):
    OPEN = "open"
    PAID = "paid"
    FAILED = "failed"
    VOID = "void"


class PaymentStatus(StrEnum):
    CREATED = "created"
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"


@dataclass(slots=True)
class Invoice:
    id: UUID
    organization_id: TenantId
    subscription_id: UUID
    number: str
    status: InvoiceStatus
    currency: str
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    tax_rate: Decimal
    total: Decimal
    line_items: list[dict[str, Any]]
    period_start: datetime
    period_end: datetime
    coupon_code: str | None = None
    provider: str | None = None
    provider_order_id: str | None = None
    issued_at: datetime = field(default_factory=utc_now)
    paid_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)

    @classmethod
    def issue(
        cls,
        *,
        organization_id: TenantId,
        subscription_id: UUID,
        number: str,
        currency: str,
        subtotal: Decimal,
        discount: Decimal,
        line_items: list[dict[str, Any]],
        period_start: datetime,
        period_end: datetime,
        coupon_code: str | None,
        tax_rate: Decimal = Decimal("0"),
    ) -> Invoice:
        taxable = subtotal - discount
        if taxable < 0:
            taxable = Decimal("0")
        tax = compute_tax(taxable, tax_rate)
        return cls(
            id=uuid4(),
            organization_id=organization_id,
            subscription_id=subscription_id,
            number=number,
            status=InvoiceStatus.OPEN,
            currency=currency.upper(),
            subtotal=subtotal,
            discount=discount,
            tax=tax,
            tax_rate=tax_rate,
            total=taxable + tax,
            line_items=line_items,
            period_start=period_start,
            period_end=period_end,
            coupon_code=coupon_code,
        )

    def attach_provider_order(self, *, provider: str, provider_order_id: str) -> None:
        self.provider = provider
        self.provider_order_id = provider_order_id

    def mark_paid(self) -> None:
        if self.status is InvoiceStatus.PAID:
            raise ConflictError("invoice is already paid")
        if self.status is InvoiceStatus.VOID:
            raise ConflictError("invoice is void")
        self.status = InvoiceStatus.PAID
        self.paid_at = utc_now()

    def mark_failed(self) -> None:
        if self.status is InvoiceStatus.OPEN:
            self.status = InvoiceStatus.FAILED

    def void(self) -> None:
        if self.status is InvoiceStatus.PAID:
            raise ConflictError("cannot void a paid invoice")
        self.status = InvoiceStatus.VOID


@dataclass(slots=True)
class Payment:
    id: UUID
    invoice_id: UUID
    organization_id: TenantId
    provider: str
    provider_payment_id: str
    amount: Decimal
    currency: str
    status: PaymentStatus
    method: str | None = None
    error: str | None = None
    refunded_amount: Decimal = Decimal("0")
    captured_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)

    def refund(self, amount: Decimal) -> None:
        if self.status is not PaymentStatus.CAPTURED:
            raise ConflictError("only a captured payment can be refunded")
        if amount <= 0:
            raise ConflictError("refund amount must be positive")
        if self.refunded_amount + amount > self.amount:
            raise ConflictError("refund exceeds the captured amount")
        self.refunded_amount += amount
        if self.refunded_amount >= self.amount:
            self.status = PaymentStatus.REFUNDED

    @classmethod
    def captured(
        cls,
        *,
        invoice_id: UUID,
        organization_id: TenantId,
        provider: str,
        provider_payment_id: str,
        amount: Decimal,
        currency: str,
        method: str | None,
    ) -> Payment:
        return cls(
            id=uuid4(),
            invoice_id=invoice_id,
            organization_id=organization_id,
            provider=provider,
            provider_payment_id=provider_payment_id,
            amount=amount,
            currency=currency.upper(),
            status=PaymentStatus.CAPTURED,
            method=method,
            captured_at=utc_now(),
        )

    @classmethod
    def failed(
        cls,
        *,
        invoice_id: UUID,
        organization_id: TenantId,
        provider: str,
        provider_payment_id: str,
        amount: Decimal,
        currency: str,
        error: str | None,
    ) -> Payment:
        return cls(
            id=uuid4(),
            invoice_id=invoice_id,
            organization_id=organization_id,
            provider=provider,
            provider_payment_id=provider_payment_id,
            amount=amount,
            currency=currency.upper(),
            status=PaymentStatus.FAILED,
            error=error,
        )
