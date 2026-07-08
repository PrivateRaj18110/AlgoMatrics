from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from algo_platform.shared.domain.errors import ValidationFailed
from algo_platform.shared.domain.types import utc_now


class PlanCode(StrEnum):
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class BillingCycle(StrEnum):
    MONTHLY = "monthly"
    YEARLY = "yearly"


def normalize_provider_prices(raw: dict[str, str]) -> dict[str, str]:
    allowed = {
        "stripe:monthly",
        "stripe:yearly",
        "razorpay:monthly",
        "razorpay:yearly",
    }
    unknown = set(raw) - allowed
    if unknown:
        raise ValidationFailed(
            "unknown provider price keys: " + ", ".join(sorted(unknown))
        )
    normalized = {key: value.strip() for key, value in raw.items() if value.strip()}
    for key, value in normalized.items():
        if len(value) > 160:
            raise ValidationFailed("provider price references must be 160 characters or fewer")
        expected_prefix = "price_" if key.startswith("stripe:") else "plan_"
        if not value.startswith(expected_prefix):
            raise ValidationFailed(
                f"{key} must use a {expected_prefix} provider reference"
            )
    return normalized


@dataclass(frozen=True, slots=True)
class PlanLimits:
    """Entitlements enforced across the platform. -1 means unlimited."""

    max_broker_connections: int
    max_active_strategies: int
    max_orders_per_day: int
    max_members: int
    max_watchlists: int
    api_access: bool
    live_trading: bool

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> PlanLimits:
        return cls(
            max_broker_connections=int(raw.get("max_broker_connections", 1)),
            max_active_strategies=int(raw.get("max_active_strategies", 1)),
            max_orders_per_day=int(raw.get("max_orders_per_day", 50)),
            max_members=int(raw.get("max_members", 1)),
            max_watchlists=int(raw.get("max_watchlists", 3)),
            api_access=bool(raw.get("api_access", False)),
            live_trading=bool(raw.get("live_trading", False)),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "max_broker_connections": self.max_broker_connections,
            "max_active_strategies": self.max_active_strategies,
            "max_orders_per_day": self.max_orders_per_day,
            "max_members": self.max_members,
            "max_watchlists": self.max_watchlists,
            "api_access": self.api_access,
            "live_trading": self.live_trading,
        }

    def allows(self, metric: str, current: int) -> bool:
        limit = int(self.to_mapping().get(metric, 0))
        return limit < 0 or current < limit


@dataclass(slots=True)
class Plan:
    id: UUID
    code: str
    name: str
    description: str
    price_monthly: Decimal
    price_yearly: Decimal
    currency: str
    features: list[str]
    limits: PlanLimits
    provider_prices: dict[str, str] = field(default_factory=dict)
    trial_days: int = 0
    is_active: bool = True
    sort_order: int = 0
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @classmethod
    def create(
        cls,
        *,
        code: str,
        name: str,
        description: str,
        price_monthly: Decimal,
        price_yearly: Decimal,
        currency: str,
        features: list[str],
        limits: PlanLimits,
        provider_prices: dict[str, str] | None = None,
        trial_days: int = 0,
        sort_order: int = 0,
    ) -> Plan:
        if price_monthly < 0 or price_yearly < 0:
            raise ValidationFailed("plan prices cannot be negative")
        if trial_days < 0 or trial_days > 90:
            raise ValidationFailed("trial period must be between 0 and 90 days")
        cleaned_code = code.strip().lower()
        if not cleaned_code:
            raise ValidationFailed("plan code is required")
        return cls(
            id=uuid4(),
            code=cleaned_code,
            name=name.strip(),
            description=description.strip(),
            price_monthly=price_monthly,
            price_yearly=price_yearly,
            currency=currency.upper(),
            features=list(features),
            limits=limits,
            provider_prices=normalize_provider_prices(provider_prices or {}),
            trial_days=trial_days,
            sort_order=sort_order,
        )

    @property
    def is_free(self) -> bool:
        return self.price_monthly == 0 and self.price_yearly == 0

    def price_for(self, cycle: BillingCycle) -> Decimal:
        return self.price_monthly if cycle is BillingCycle.MONTHLY else self.price_yearly

    def provider_price(self, provider: str, cycle: BillingCycle) -> str | None:
        value = self.provider_prices.get(f"{provider}:{cycle.value}", "").strip()
        return value or None
