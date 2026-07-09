"""Unit tests for the marketplace domain (Phase 10, slice A)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from algo_platform.modules.marketplace.domain.marketplace import (
    License,
    LicenseKind,
    Listing,
    ListingStatus,
    PricingModel,
    Review,
    revenue_split,
)
from algo_platform.shared.domain.errors import ConflictError, ValidationFailed
from algo_platform.shared.domain.types import TenantId, utc_now


def _listing(**over: object) -> Listing:
    base: dict[str, object] = {
        "strategy_id": uuid4(),
        "publisher_org_id": TenantId(uuid4()),
        "title": "Momentum Pro",
        "summary": "A momentum strategy",
        "pricing_model": PricingModel.ONE_TIME,
        "price": Decimal("1000"),
        "currency": "INR",
    }
    base.update(over)
    return Listing.draft(**base)  # type: ignore[arg-type]


def test_revenue_split_rounds_and_sums() -> None:
    publisher, platform = revenue_split(Decimal("999.99"), Decimal("70"))
    assert publisher == Decimal("699.99")
    assert publisher + platform == Decimal("999.99")


def test_revenue_split_clamps_share() -> None:
    assert revenue_split(Decimal("100"), Decimal("150")) == (Decimal("100.00"), Decimal("0.00"))
    assert revenue_split(Decimal("100"), Decimal("-5")) == (Decimal("0.00"), Decimal("100.00"))


def test_free_listing_requires_zero_price() -> None:
    with pytest.raises(ValidationFailed):
        _listing(pricing_model=PricingModel.FREE, price=Decimal("10"))
    free = _listing(pricing_model=PricingModel.FREE, price=Decimal("0"))
    assert free.is_free


def test_paid_listing_requires_positive_price() -> None:
    with pytest.raises(ValidationFailed):
        _listing(price=Decimal("0"))


def test_title_length_validated() -> None:
    with pytest.raises(ValidationFailed):
        _listing(title="ab")


def test_publish_and_unlist_lifecycle() -> None:
    listing = _listing()
    assert listing.status is ListingStatus.DRAFT
    listing.publish()
    assert listing.status is ListingStatus.PUBLISHED
    with pytest.raises(ConflictError):
        listing.publish()
    listing.unlist()
    assert listing.status is ListingStatus.UNLISTED


def test_listing_earnings_uses_share() -> None:
    listing = _listing(revenue_share_percent=Decimal("80"))
    publisher, platform = listing.earnings_for(Decimal("1000"))
    assert publisher == Decimal("800.00")
    assert platform == Decimal("200.00")


def test_review_rating_bounds() -> None:
    with pytest.raises(ValidationFailed):
        Review.create(listing_id=uuid4(), reviewer_org_id=TenantId(uuid4()), rating=6, comment="x")
    review = Review.create(
        listing_id=uuid4(), reviewer_org_id=TenantId(uuid4()), rating=5, comment="great"
    )
    assert review.rating == 5


def test_license_active_and_expiry() -> None:
    lic = License.grant(
        listing_id=uuid4(), licensee_org_id=TenantId(uuid4()), kind=LicenseKind.PURCHASE
    )
    assert lic.is_active()
    lic.revoke()
    assert not lic.is_active()

    expired = License.grant(
        listing_id=uuid4(),
        licensee_org_id=TenantId(uuid4()),
        kind=LicenseKind.SUBSCRIPTION,
        expires_at=utc_now() - timedelta(days=1),
    )
    assert not expired.is_active()
