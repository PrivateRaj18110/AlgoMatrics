"""Marketplace application service: publish, browse, review, license."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.marketplace.domain.marketplace import (
    License,
    LicenseKind,
    Listing,
    PricingModel,
    Review,
    revenue_split,
)
from algo_platform.modules.marketplace.infrastructure.repositories import (
    ListingStats,
    SqlMarketplaceRepository,
)
from algo_platform.shared.domain.errors import ConflictError, NotFoundError
from algo_platform.shared.domain.types import TenantId


@dataclass(frozen=True, slots=True)
class ListingView:
    listing: Listing
    stats: ListingStats


@dataclass(frozen=True, slots=True)
class RevenueReport:
    currency: str
    gross: Decimal
    publisher_earnings: Decimal
    platform_fee: Decimal
    license_count: int


class MarketplaceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = SqlMarketplaceRepository(session)

    async def publish(
        self,
        *,
        publisher_org_id: TenantId,
        strategy_id: UUID,
        title: str,
        summary: str,
        pricing_model: PricingModel,
        price: Decimal,
        currency: str,
        revenue_share_percent: Decimal = Decimal("70"),
    ) -> Listing:
        listing = Listing.draft(
            strategy_id=strategy_id,
            publisher_org_id=publisher_org_id,
            title=title,
            summary=summary,
            pricing_model=pricing_model,
            price=price,
            currency=currency,
            revenue_share_percent=revenue_share_percent,
        )
        listing.publish()
        await self._repo.add_listing(listing)
        return listing

    async def unlist(self, listing_id: UUID, publisher_org_id: TenantId) -> None:
        listing = await self._owned_listing(listing_id, publisher_org_id)
        listing.unlist()
        await self._repo.save_listing(listing)

    async def browse(self, *, limit: int, offset: int) -> list[ListingView]:
        listings = await self._repo.list_published(limit=limit, offset=offset)
        return [
            ListingView(listing=listing, stats=await self._repo.stats(listing.id))
            for listing in listings
        ]

    async def detail(self, listing_id: UUID) -> tuple[ListingView, list[Review]]:
        listing = await self._repo.get_listing(listing_id)
        if listing is None:
            raise NotFoundError("listing not found")
        stats = await self._repo.stats(listing_id)
        reviews = await self._repo.list_reviews(listing_id)
        return ListingView(listing=listing, stats=stats), reviews

    async def acquire_license(
        self, listing_id: UUID, licensee_org_id: TenantId, *, expires_at: datetime | None = None
    ) -> License:
        listing = await self._repo.get_listing(listing_id)
        if listing is None:
            raise NotFoundError("listing not found")
        if listing.publisher_org_id == licensee_org_id:
            raise ConflictError("you cannot license your own strategy")
        existing = await self._repo.get_license(listing_id, licensee_org_id)
        if existing is not None and existing.is_active():
            raise ConflictError("you already hold an active license for this listing")
        kind = (
            LicenseKind.SUBSCRIPTION
            if listing.pricing_model is PricingModel.SUBSCRIPTION
            else LicenseKind.PURCHASE
        )
        # Paid licenses are recorded here; payment capture is handled by billing
        # before this call in the presentation layer.
        license_ = License.grant(
            listing_id=listing_id,
            licensee_org_id=licensee_org_id,
            kind=kind,
            expires_at=expires_at,
        )
        await self._repo.add_license(license_)
        return license_

    async def review(
        self, listing_id: UUID, reviewer_org_id: TenantId, *, rating: int, comment: str
    ) -> Review:
        listing = await self._repo.get_listing(listing_id)
        if listing is None:
            raise NotFoundError("listing not found")
        held = await self._repo.get_license(listing_id, reviewer_org_id)
        if held is None:
            raise ConflictError("only organizations that have licensed this strategy can review it")
        existing = await self._repo.list_reviews(listing_id)
        if any(r.reviewer_org_id == reviewer_org_id for r in existing):
            raise ConflictError("you have already reviewed this listing")
        review = Review.create(
            listing_id=listing_id,
            reviewer_org_id=reviewer_org_id,
            rating=rating,
            comment=comment,
        )
        await self._repo.add_review(review)
        return review

    async def my_licenses(self, org_id: TenantId) -> list[License]:
        return await self._repo.list_licenses_for_org(org_id)

    async def revenue_report(self, publisher_org_id: TenantId) -> list[RevenueReport]:
        """Gross and split earnings per currency across the publisher's listings."""
        listings = await self._repo.list_published(limit=1000, offset=0)
        owned = [item for item in listings if item.publisher_org_id == publisher_org_id]
        by_currency: dict[str, RevenueReport] = {}
        for listing in owned:
            stats = await self._repo.stats(listing.id)
            gross = listing.price * stats.license_count
            publisher, platform = revenue_split(gross, listing.revenue_share_percent)
            prior = by_currency.get(listing.currency)
            if prior is None:
                by_currency[listing.currency] = RevenueReport(
                    currency=listing.currency,
                    gross=gross,
                    publisher_earnings=publisher,
                    platform_fee=platform,
                    license_count=stats.license_count,
                )
            else:
                by_currency[listing.currency] = RevenueReport(
                    currency=listing.currency,
                    gross=prior.gross + gross,
                    publisher_earnings=prior.publisher_earnings + publisher,
                    platform_fee=prior.platform_fee + platform,
                    license_count=prior.license_count + stats.license_count,
                )
        return list(by_currency.values())

    async def _owned_listing(self, listing_id: UUID, publisher_org_id: TenantId) -> Listing:
        listing = await self._repo.get_listing(listing_id)
        if listing is None:
            raise NotFoundError("listing not found")
        if listing.publisher_org_id != publisher_org_id:
            raise ConflictError("you do not own this listing")
        return listing
