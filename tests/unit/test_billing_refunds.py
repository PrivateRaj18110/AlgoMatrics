"""Unit tests for payment refunds (Phase 9, slice B)."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from algo_platform.modules.billing.domain.invoices import Payment, PaymentStatus
from algo_platform.shared.domain.errors import ConflictError
from algo_platform.shared.domain.types import TenantId


def _captured(amount: str = "1000") -> Payment:
    return Payment.captured(
        invoice_id=uuid4(),
        organization_id=TenantId(uuid4()),
        provider="stripe",
        provider_payment_id="pi_1",
        amount=Decimal(amount),
        currency="INR",
        method="card",
    )


def test_full_refund_marks_refunded() -> None:
    payment = _captured("1000")
    payment.refund(Decimal("1000"))
    assert payment.refunded_amount == Decimal("1000")
    assert payment.status is PaymentStatus.REFUNDED


def test_partial_refund_keeps_captured() -> None:
    payment = _captured("1000")
    payment.refund(Decimal("400"))
    assert payment.refunded_amount == Decimal("400")
    assert payment.status is PaymentStatus.CAPTURED
    # A second partial refund accumulates and can complete it.
    payment.refund(Decimal("600"))
    assert payment.status is PaymentStatus.REFUNDED


def test_refund_cannot_exceed_captured() -> None:
    payment = _captured("1000")
    payment.refund(Decimal("700"))
    with pytest.raises(ConflictError, match="exceeds"):
        payment.refund(Decimal("400"))


def test_refund_rejects_non_positive() -> None:
    with pytest.raises(ConflictError):
        _captured().refund(Decimal("0"))


def test_only_captured_can_be_refunded() -> None:
    payment = Payment.failed(
        invoice_id=uuid4(),
        organization_id=TenantId(uuid4()),
        provider="stripe",
        provider_payment_id="pi_1",
        amount=Decimal("1000"),
        currency="INR",
        error="declined",
    )
    with pytest.raises(ConflictError, match="captured"):
        payment.refund(Decimal("100"))
