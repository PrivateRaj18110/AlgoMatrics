"""Tax computation for invoices (India GST-aware, framework-free).

A single tax rate is applied to the post-discount taxable amount. For Indian GST
the resulting tax is presented as a CGST/SGST split (intra-state) or IGST
(inter-state); the total tax figure is what the invoice stores.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

_CENTS = Decimal("0.01")


def quantize_money(amount: Decimal) -> Decimal:
    return amount.quantize(_CENTS, rounding=ROUND_HALF_UP)


def compute_tax(taxable: Decimal, rate_percent: Decimal) -> Decimal:
    """Return the tax due on ``taxable`` at ``rate_percent`` (e.g. 18 for 18%)."""
    if taxable <= 0 or rate_percent <= 0:
        return Decimal("0.00")
    return quantize_money(taxable * rate_percent / Decimal("100"))


@dataclass(frozen=True, slots=True)
class GstBreakdown:
    cgst: Decimal
    sgst: Decimal
    igst: Decimal

    def as_line_items(self, rate_percent: Decimal) -> list[dict[str, str]]:
        half = (rate_percent / 2).normalize()
        if self.igst > 0:
            return [{"label": f"IGST @ {rate_percent}%", "amount": str(self.igst)}]
        if self.cgst > 0 or self.sgst > 0:
            return [
                {"label": f"CGST @ {half}%", "amount": str(self.cgst)},
                {"label": f"SGST @ {half}%", "amount": str(self.sgst)},
            ]
        return []


def gst_breakdown(tax: Decimal, *, intra_state: bool) -> GstBreakdown:
    """Split a total GST amount into CGST/SGST (intra-state) or IGST (inter-state)."""
    if tax <= 0:
        return GstBreakdown(cgst=Decimal("0.00"), sgst=Decimal("0.00"), igst=Decimal("0.00"))
    if intra_state:
        half = quantize_money(tax / 2)
        # Put any rounding remainder on CGST so the halves still sum to `tax`.
        return GstBreakdown(cgst=tax - half, sgst=half, igst=Decimal("0.00"))
    return GstBreakdown(cgst=Decimal("0.00"), sgst=Decimal("0.00"), igst=tax)
