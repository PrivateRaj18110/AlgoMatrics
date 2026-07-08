"""Risk aggregates: limits, kill switches, and pre-trade decisions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from algo_platform.shared.domain.errors import ConflictError, ValidationFailed
from algo_platform.shared.domain.types import AccountId, TenantId, UserId, utc_now

DEFAULT_MAX_ORDER_QUANTITY = Decimal("100000")
DEFAULT_MAX_ORDER_VALUE = Decimal("10000000")
DEFAULT_MAX_DAILY_LOSS = Decimal("100000")
DEFAULT_MAX_OPEN_POSITIONS = 25
DEFAULT_MAX_EXPOSURE = Decimal("50000000")
DEFAULT_MAX_DRAWDOWN_PCT = Decimal("25")


@dataclass(slots=True)
class RiskLimits:
    """Per-organization limits with optional per-account overrides."""

    id: UUID
    organization_id: TenantId
    account_id: AccountId | None
    max_order_quantity: Decimal
    max_order_value: Decimal
    max_daily_loss: Decimal
    max_open_positions: int
    max_exposure_value: Decimal
    max_drawdown_pct: Decimal
    is_active: bool = True
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @classmethod
    def defaults(
        cls, *, organization_id: TenantId, account_id: AccountId | None = None
    ) -> RiskLimits:
        return cls(
            id=uuid4(),
            organization_id=organization_id,
            account_id=account_id,
            max_order_quantity=DEFAULT_MAX_ORDER_QUANTITY,
            max_order_value=DEFAULT_MAX_ORDER_VALUE,
            max_daily_loss=DEFAULT_MAX_DAILY_LOSS,
            max_open_positions=DEFAULT_MAX_OPEN_POSITIONS,
            max_exposure_value=DEFAULT_MAX_EXPOSURE,
            max_drawdown_pct=DEFAULT_MAX_DRAWDOWN_PCT,
        )

    def update(self, changes: dict[str, Any]) -> None:
        decimal_fields = {
            "max_order_quantity",
            "max_order_value",
            "max_daily_loss",
            "max_exposure_value",
            "max_drawdown_pct",
        }
        for key, value in changes.items():
            if key in decimal_fields:
                amount = Decimal(str(value))
                if amount <= 0:
                    raise ValidationFailed(f"{key} must be positive")
                setattr(self, key, amount)
            elif key == "max_open_positions":
                count = int(value)
                if count <= 0 or count > 10_000:
                    raise ValidationFailed("max_open_positions must be 1-10000")
                self.max_open_positions = count
            elif key == "is_active":
                self.is_active = bool(value)
            else:
                raise ValidationFailed(f"unknown risk limit field: {key}")
        self.updated_at = utc_now()


class KillSwitchScope(StrEnum):
    ORGANIZATION = "organization"
    ACCOUNT = "account"
    STRATEGY = "strategy"


@dataclass(slots=True)
class KillSwitch:
    id: UUID
    organization_id: TenantId
    scope: KillSwitchScope
    scope_ref: str
    reason: str
    engaged_by: UserId
    engaged_at: datetime = field(default_factory=utc_now)
    released_at: datetime | None = None
    released_by: UserId | None = None

    @classmethod
    def engage(
        cls,
        *,
        organization_id: TenantId,
        scope: KillSwitchScope,
        scope_ref: str,
        reason: str,
        engaged_by: UserId,
    ) -> KillSwitch:
        cleaned = reason.strip()
        if not cleaned:
            raise ValidationFailed("a reason is required to engage a kill switch")
        return cls(
            id=uuid4(),
            organization_id=organization_id,
            scope=scope,
            scope_ref=scope_ref,
            reason=cleaned,
            engaged_by=engaged_by,
        )

    @property
    def is_engaged(self) -> bool:
        return self.released_at is None

    def release(self, released_by: UserId) -> None:
        if self.released_at is not None:
            raise ConflictError("kill switch is already released")
        self.released_at = utc_now()
        self.released_by = released_by


class RiskDecisionResult(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class RiskDecision:
    id: UUID
    organization_id: TenantId
    order_id: UUID
    result: RiskDecisionResult
    reason_codes: list[str]
    inputs: dict[str, Any]
    policy_version: int
    decided_at: datetime

    @classmethod
    def make(
        cls,
        *,
        organization_id: TenantId,
        order_id: UUID,
        result: RiskDecisionResult,
        reason_codes: list[str],
        inputs: dict[str, Any],
        policy_version: int = 1,
    ) -> RiskDecision:
        return cls(
            id=uuid4(),
            organization_id=organization_id,
            order_id=order_id,
            result=result,
            reason_codes=reason_codes,
            inputs=inputs,
            policy_version=policy_version,
            decided_at=utc_now(),
        )
