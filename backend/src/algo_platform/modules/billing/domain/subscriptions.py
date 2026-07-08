from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

from algo_platform.modules.billing.domain.plans import BillingCycle
from algo_platform.shared.domain.errors import ConflictError, InvariantViolation
from algo_platform.shared.domain.types import TenantId, utc_now

PAST_DUE_GRACE_DAYS = 7


class SubscriptionStatus(StrEnum):
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


def period_delta(cycle: BillingCycle) -> timedelta:
    return timedelta(days=30) if cycle is BillingCycle.MONTHLY else timedelta(days=365)


@dataclass(slots=True)
class Subscription:
    id: UUID
    organization_id: TenantId
    plan_id: UUID
    status: SubscriptionStatus
    billing_cycle: BillingCycle
    current_period_start: datetime
    current_period_end: datetime
    trial_end: datetime | None = None
    trial_used: bool = False
    cancel_at_period_end: bool = False
    pending_plan_id: UUID | None = None
    provider: str | None = None
    provider_ref: str | None = None
    provider_customer_id: str | None = None
    provider_price_ref: str | None = None
    provider_status: str | None = None
    last_provider_event_at: datetime | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    version: int = 1

    @classmethod
    def start_free(cls, *, organization_id: TenantId, plan_id: UUID) -> Subscription:
        now = utc_now()
        return cls(
            id=uuid4(),
            organization_id=organization_id,
            plan_id=plan_id,
            status=SubscriptionStatus.ACTIVE,
            billing_cycle=BillingCycle.MONTHLY,
            current_period_start=now,
            # Free plans do not expire; the far-future end keeps queries uniform.
            current_period_end=now + timedelta(days=36500),
        )

    def start_trial(self, *, plan_id: UUID, trial_days: int, cycle: BillingCycle) -> None:
        if self.trial_used:
            raise ConflictError("trial already used for this organization")
        if trial_days <= 0:
            raise InvariantViolation("plan does not offer a trial")
        now = utc_now()
        self.plan_id = plan_id
        self.status = SubscriptionStatus.TRIALING
        self.billing_cycle = cycle
        self.current_period_start = now
        self.current_period_end = now + timedelta(days=trial_days)
        self.trial_end = self.current_period_end
        self.trial_used = True
        self.cancel_at_period_end = False
        self.pending_plan_id = None
        self.touch()

    def activate_paid(
        self, *, plan_id: UUID, cycle: BillingCycle, provider: str, provider_ref: str | None
    ) -> None:
        now = utc_now()
        self.plan_id = plan_id
        self.status = SubscriptionStatus.ACTIVE
        self.billing_cycle = cycle
        self.current_period_start = now
        self.current_period_end = now + period_delta(cycle)
        self.trial_end = None
        self.cancel_at_period_end = False
        self.pending_plan_id = None
        self.provider = provider
        self.provider_ref = provider_ref
        self.provider_status = "active"
        self.touch()

    def sync_provider(
        self,
        *,
        status: SubscriptionStatus,
        provider_status: str,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
        provider_ref: str | None = None,
        customer_id: str | None = None,
        price_ref: str | None = None,
        event_at: datetime | None = None,
    ) -> None:
        self.status = status
        self.provider_status = provider_status
        if period_start is not None:
            self.current_period_start = period_start
        if period_end is not None:
            self.current_period_end = period_end
        if provider_ref:
            self.provider_ref = provider_ref
        if customer_id:
            self.provider_customer_id = customer_id
        if price_ref:
            self.provider_price_ref = price_ref
        self.last_provider_event_at = event_at or utc_now()
        self.touch()

    def schedule_plan_change(self, plan_id: UUID) -> None:
        if plan_id == self.plan_id:
            raise ConflictError("subscription is already on this plan")
        self.pending_plan_id = plan_id
        self.touch()

    def request_cancellation(self) -> None:
        if self.status not in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING}:
            raise ConflictError("only active subscriptions can be cancelled")
        if self.cancel_at_period_end:
            raise ConflictError("cancellation is already scheduled")
        self.cancel_at_period_end = True
        self.touch()

    def resume(self) -> None:
        if not self.cancel_at_period_end:
            raise ConflictError("no pending cancellation to resume from")
        self.cancel_at_period_end = False
        self.touch()

    def mark_past_due(self) -> None:
        if self.status is SubscriptionStatus.ACTIVE:
            self.status = SubscriptionStatus.PAST_DUE
            self.touch()

    def apply_period_rollover(self, *, fallback_plan_id: UUID) -> None:
        """Apply scheduled changes at period end (called by the scheduler)."""
        now = utc_now()
        if self.current_period_end > now:
            return
        if self.cancel_at_period_end or self.status in {
            SubscriptionStatus.PAST_DUE,
            SubscriptionStatus.TRIALING,
        }:
            # Trial ended without payment / cancelled / unpaid: fall back to free.
            self.plan_id = self.pending_plan_id or fallback_plan_id
            if self.cancel_at_period_end or self.status is not SubscriptionStatus.TRIALING:
                self.plan_id = fallback_plan_id
            self.status = SubscriptionStatus.ACTIVE
            self.billing_cycle = BillingCycle.MONTHLY
            self.current_period_start = now
            self.current_period_end = now + timedelta(days=36500)
            self.cancel_at_period_end = False
            self.pending_plan_id = None
            self.provider = None
            self.provider_ref = None
            self.provider_customer_id = None
            self.provider_price_ref = None
            self.provider_status = None
            self.touch()
        elif self.pending_plan_id is not None:
            # Scheduled downgrade to another paid plan requires a fresh payment;
            # until paid, the account falls back to free entitlements.
            self.plan_id = fallback_plan_id
            self.status = SubscriptionStatus.ACTIVE
            self.current_period_start = now
            self.current_period_end = now + timedelta(days=36500)
            self.pending_plan_id = None
            self.touch()
        else:
            # Renewal expected but not received yet: grace period, then past due.
            self.mark_past_due()

    def touch(self) -> None:
        self.updated_at = utc_now()

    @property
    def in_paid_period(self) -> bool:
        return (
            self.status in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING}
            and self.current_period_end > utc_now()
        )
