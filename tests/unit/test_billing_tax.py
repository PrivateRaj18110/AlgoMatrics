"""Unit tests for invoice tax / GST (Phase 9, slice A)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from algo_platform.modules.billing.domain.invoices import Invoice
from algo_platform.modules.billing.domain.tax import (
    compute_tax,
    gst_breakdown,
)
from algo_platform.shared.domain.types import TenantId


def test_compute_tax_rounds_to_cents() -> None:
    assert compute_tax(Decimal("1000"), Decimal("18")) == Decimal("180.00")
    assert compute_tax(Decimal("999.99"), Decimal("18")) == Decimal("180.00")
    assert compute_tax(Decimal("0"), Decimal("18")) == Decimal("0.00")
    assert compute_tax(Decimal("1000"), Decimal("0")) == Decimal("0.00")


def test_gst_intra_state_splits_cgst_sgst() -> None:
    breakdown = gst_breakdown(Decimal("180.00"), intra_state=True)
    assert breakdown.cgst == Decimal("90.00")
    assert breakdown.sgst == Decimal("90.00")
    assert breakdown.igst == Decimal("0.00")


def test_gst_odd_amount_halves_sum_to_total() -> None:
    breakdown = gst_breakdown(Decimal("18.05"), intra_state=True)
    assert breakdown.cgst + breakdown.sgst == Decimal("18.05")


def test_gst_inter_state_uses_igst() -> None:
    breakdown = gst_breakdown(Decimal("180.00"), intra_state=False)
    assert breakdown.igst == Decimal("180.00")
    assert breakdown.cgst == Decimal("0.00")


def _issue(subtotal: str, discount: str, rate: str) -> Invoice:
    now = datetime(2026, 7, 8, tzinfo=UTC)
    return Invoice.issue(
        organization_id=TenantId(uuid4()),
        subscription_id=uuid4(),
        number="INV-1",
        currency="INR",
        subtotal=Decimal(subtotal),
        discount=Decimal(discount),
        line_items=[],
        period_start=now,
        period_end=now,
        coupon_code=None,
        tax_rate=Decimal(rate),
    )


def test_invoice_total_includes_tax_on_post_discount_amount() -> None:
    invoice = _issue("1000", "100", "18")
    # taxable = 900, tax = 162, total = 1062
    assert invoice.tax == Decimal("162.00")
    assert invoice.tax_rate == Decimal("18")
    assert invoice.total == Decimal("1062.00")


def test_invoice_zero_rate_has_no_tax() -> None:
    invoice = _issue("1000", "0", "0")
    assert invoice.tax == Decimal("0.00")
    assert invoice.total == Decimal("1000")


def test_invoice_discount_exceeding_subtotal_taxes_zero() -> None:
    invoice = _issue("100", "150", "18")
    assert invoice.tax == Decimal("0.00")
    assert invoice.total == Decimal("0")
