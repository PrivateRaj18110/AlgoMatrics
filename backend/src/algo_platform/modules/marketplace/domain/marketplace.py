"""Marketplace aggregates: listings, reviews, and licenses.

A publisher organization lists one of its strategies for others to license. The
domain is framework-free and holds the invariants: pricing/revenue split,
review validity, and license lifecycle. Money is split between the publisher
and the platform by ``revenue_share_percent`` (the publisher's cut).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from algo_platform.shared.domain.errors import ConflictError, ValidationFailed
from algo_platform.shared.domain.types import TenantId, utc_now

_CENTS = Decimal("0.01")


class ListingStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    UNLISTED = "unlisted"


class PricingModel(StrEnum):
    FREE = "free"
    ONE_TIME = "one_time"
    SUBSCRIPTION = "subscription"


class LicenseKind(StrEnum):
    PURCHASE = "purchase"
    SUBSCRIPTION = "subscription"


class LicenseStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


def revenue_split(gross: Decimal, revenue_share_percent: Decimal) -> tuple[Decimal, Decimal]:
    """Split ``gross`` into (publisher_earnings, platform_fee), rounded to cents."""
    share = max(Decimal("0"), min(Decimal("100"), revenue_share_percent))
    publisher = (gross * share / Decimal("100")).quantize(_CENTS, rounding=ROUND_HALF_UP)
    platform = gross - publisher
    return publisher, platform


@dataclass(slots=True)
class Listing:
    id: UUID
    strategy_id: UUID
    publisher_org_id: TenantId
    title: str
    summary: str
    status: ListingStatus
    pricing_model: PricingModel
    price: Decimal
    currency: str
    revenue_share_percent: Decimal
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @classmethod
    def draft(
        cls,
        *,
        strategy_id: UUID,
        publisher_org_id: TenantId,
        title: str,
        summary: str,
        pricing_model: PricingModel,
        price: Decimal,
        currency: str,
        revenue_share_percent: Decimal = Decimal("70"),
    ) -> Listing:
        clean_title = title.strip()
        if not 3 <= len(clean_title) <= 120:
            raise ValidationFailed("listing title must be 3-120 characters")
        if pricing_model is PricingModel.FREE and price != 0:
            raise ValidationFailed("free listings must have a zero price")
        if pricing_model is not PricingModel.FREE and price <= 0:
            raise ValidationFailed("paid listings must have a positive price")
        if not 0 <= revenue_share_percent <= 100:
            raise ValidationFailed("revenue share must be between 0 and 100")
        return cls(
            id=uuid4(),
            strategy_id=strategy_id,
            publisher_org_id=publisher_org_id,
            title=clean_title,
            summary=summary.strip()[:2000],
            status=ListingStatus.DRAFT,
            pricing_model=pricing_model,
            price=price,
            currency=currency.upper(),
            revenue_share_percent=revenue_share_percent,
        )

    def publish(self) -> None:
        if self.status is ListingStatus.PUBLISHED:
            raise ConflictError("listing is already published")
        self.status = ListingStatus.PUBLISHED
        self.updated_at = utc_now()

    def unlist(self) -> None:
        if self.status is not ListingStatus.PUBLISHED:
            raise ConflictError("only a published listing can be unlisted")
        self.status = ListingStatus.UNLISTED
        self.updated_at = utc_now()

    @property
    def is_free(self) -> bool:
        return self.pricing_model is PricingModel.FREE

    def earnings_for(self, gross: Decimal) -> tuple[Decimal, Decimal]:
        return revenue_split(gross, self.revenue_share_percent)


@dataclass(slots=True)
class Review:
    id: UUID
    listing_id: UUID
    reviewer_org_id: TenantId
    rating: int
    comment: str
    created_at: datetime = field(default_factory=utc_now)

    @classmethod
    def create(
        cls,
        *,
        listing_id: UUID,
        reviewer_org_id: TenantId,
        rating: int,
        comment: str,
    ) -> Review:
        if not 1 <= rating <= 5:
            raise ValidationFailed("rating must be between 1 and 5")
        return cls(
            id=uuid4(),
            listing_id=listing_id,
            reviewer_org_id=reviewer_org_id,
            rating=rating,
            comment=comment.strip()[:2000],
        )


@dataclass(slots=True)
class License:
    id: UUID
    listing_id: UUID
    licensee_org_id: TenantId
    kind: LicenseKind
    status: LicenseStatus
    granted_at: datetime = field(default_factory=utc_now)
    expires_at: datetime | None = None

    @classmethod
    def grant(
        cls,
        *,
        listing_id: UUID,
        licensee_org_id: TenantId,
        kind: LicenseKind,
        expires_at: datetime | None = None,
    ) -> License:
        return cls(
            id=uuid4(),
            listing_id=listing_id,
            licensee_org_id=licensee_org_id,
            kind=kind,
            status=LicenseStatus.ACTIVE,
            expires_at=expires_at,
        )

    def is_active(self, *, now: datetime | None = None) -> bool:
        moment = now or utc_now()
        if self.status is not LicenseStatus.ACTIVE:
            return False
        return self.expires_at is None or self.expires_at > moment

    def revoke(self) -> None:
        self.status = LicenseStatus.REVOKED
