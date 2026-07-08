from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID, uuid4

from algo_platform.shared.domain.errors import ConflictError, ValidationFailed
from algo_platform.shared.domain.types import utc_now


@dataclass(slots=True)
class Coupon:
    id: UUID
    code: str
    description: str
    percent_off: Decimal | None
    amount_off: Decimal | None
    currency: str
    max_redemptions: int | None
    redeemed_count: int
    valid_from: datetime | None
    valid_until: datetime | None
    is_active: bool
    applies_plan_codes: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @classmethod
    def create(
        cls,
        *,
        code: str,
        description: str,
        percent_off: Decimal | None,
        amount_off: Decimal | None,
        currency: str,
        max_redemptions: int | None,
        valid_from: datetime | None,
        valid_until: datetime | None,
        applies_plan_codes: list[str],
    ) -> Coupon:
        cleaned = code.strip().upper()
        if not cleaned or len(cleaned) > 40:
            raise ValidationFailed("coupon code must be 1-40 characters")
        if (percent_off is None) == (amount_off is None):
            raise ValidationFailed("provide exactly one of percent_off or amount_off")
        if percent_off is not None and not (0 < percent_off <= 100):
            raise ValidationFailed("percent_off must be between 0 and 100")
        if amount_off is not None and amount_off <= 0:
            raise ValidationFailed("amount_off must be positive")
        if valid_from and valid_until and valid_from >= valid_until:
            raise ValidationFailed("valid_from must precede valid_until")
        return cls(
            id=uuid4(),
            code=cleaned,
            description=description.strip(),
            percent_off=percent_off,
            amount_off=amount_off,
            currency=currency.upper(),
            max_redemptions=max_redemptions,
            redeemed_count=0,
            valid_from=valid_from,
            valid_until=valid_until,
            is_active=True,
            applies_plan_codes=[c.lower() for c in applies_plan_codes],
        )

    def ensure_redeemable(self, *, plan_code: str, currency: str) -> None:
        now = utc_now()
        if not self.is_active:
            raise ConflictError("coupon is not active")
        if self.valid_from is not None and now < self.valid_from:
            raise ConflictError("coupon is not valid yet")
        if self.valid_until is not None and now > self.valid_until:
            raise ConflictError("coupon has expired")
        if self.max_redemptions is not None and self.redeemed_count >= self.max_redemptions:
            raise ConflictError("coupon redemption limit reached")
        if self.applies_plan_codes and plan_code.lower() not in self.applies_plan_codes:
            raise ConflictError("coupon does not apply to this plan")
        if self.amount_off is not None and self.currency != currency.upper():
            raise ConflictError("coupon currency does not match the plan currency")

    def discount_for(self, amount: Decimal) -> Decimal:
        if self.percent_off is not None:
            discount = (amount * self.percent_off / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            discount = self.amount_off or Decimal("0")
        return min(discount, amount)

    def record_redemption(self) -> None:
        if self.max_redemptions is not None and self.redeemed_count >= self.max_redemptions:
            raise ConflictError("coupon redemption limit reached")
        self.redeemed_count += 1
        self.updated_at = utc_now()
