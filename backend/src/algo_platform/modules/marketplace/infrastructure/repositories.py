from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.marketplace.domain.marketplace import (
    License,
    LicenseKind,
    LicenseStatus,
    Listing,
    ListingStatus,
    PricingModel,
    Review,
)
from algo_platform.modules.marketplace.infrastructure.models import (
    MarketplaceLicenseModel,
    MarketplaceListingModel,
    MarketplaceReviewModel,
)
from algo_platform.shared.domain.types import TenantId


@dataclass(frozen=True, slots=True)
class ListingStats:
    review_count: int
    average_rating: float
    license_count: int


def _listing_to_entity(m: MarketplaceListingModel) -> Listing:
    return Listing(
        id=m.id,
        strategy_id=m.strategy_id,
        publisher_org_id=TenantId(m.publisher_org_id),
        title=m.title,
        summary=m.summary,
        status=ListingStatus(m.status),
        pricing_model=PricingModel(m.pricing_model),
        price=m.price,
        currency=m.currency,
        revenue_share_percent=m.revenue_share_percent,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


class SqlMarketplaceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- listings ----------------------------------------------------------
    async def add_listing(self, listing: Listing) -> None:
        self._session.add(
            MarketplaceListingModel(
                id=listing.id,
                strategy_id=listing.strategy_id,
                publisher_org_id=listing.publisher_org_id,
                title=listing.title,
                summary=listing.summary,
                status=listing.status.value,
                pricing_model=listing.pricing_model.value,
                price=listing.price,
                currency=listing.currency,
                revenue_share_percent=listing.revenue_share_percent,
                created_at=listing.created_at,
                updated_at=listing.updated_at,
            )
        )
        await self._session.flush()

    async def get_listing(self, listing_id: UUID) -> Listing | None:
        model = await self._session.get(MarketplaceListingModel, listing_id)
        return _listing_to_entity(model) if model is not None else None

    async def save_listing(self, listing: Listing) -> None:
        model = await self._session.get(MarketplaceListingModel, listing.id)
        if model is None:
            return
        model.status = listing.status.value
        model.updated_at = listing.updated_at

    async def list_published(self, *, limit: int, offset: int) -> list[Listing]:
        rows = (
            await self._session.execute(
                select(MarketplaceListingModel)
                .where(MarketplaceListingModel.status == ListingStatus.PUBLISHED.value)
                .order_by(MarketplaceListingModel.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
        return [_listing_to_entity(m) for m in rows]

    async def stats(self, listing_id: UUID) -> ListingStats:
        review_row = (
            await self._session.execute(
                select(func.count(), func.coalesce(func.avg(MarketplaceReviewModel.rating), 0))
                .where(MarketplaceReviewModel.listing_id == listing_id)
            )
        ).one()
        license_count = (
            await self._session.execute(
                select(func.count())
                .select_from(MarketplaceLicenseModel)
                .where(MarketplaceLicenseModel.listing_id == listing_id)
            )
        ).scalar_one()
        return ListingStats(
            review_count=int(review_row[0]),
            average_rating=round(float(review_row[1]), 2),
            license_count=int(license_count),
        )

    # -- reviews -----------------------------------------------------------
    async def add_review(self, review: Review) -> None:
        self._session.add(
            MarketplaceReviewModel(
                id=review.id,
                listing_id=review.listing_id,
                reviewer_org_id=review.reviewer_org_id,
                rating=review.rating,
                comment=review.comment,
                created_at=review.created_at,
            )
        )
        await self._session.flush()

    async def list_reviews(self, listing_id: UUID, *, limit: int = 50) -> list[Review]:
        rows = (
            await self._session.execute(
                select(MarketplaceReviewModel)
                .where(MarketplaceReviewModel.listing_id == listing_id)
                .order_by(MarketplaceReviewModel.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [
            Review(
                id=m.id,
                listing_id=m.listing_id,
                reviewer_org_id=TenantId(m.reviewer_org_id),
                rating=m.rating,
                comment=m.comment,
                created_at=m.created_at,
            )
            for m in rows
        ]

    # -- licenses ----------------------------------------------------------
    async def add_license(self, license_: License) -> None:
        self._session.add(
            MarketplaceLicenseModel(
                id=license_.id,
                listing_id=license_.listing_id,
                licensee_org_id=license_.licensee_org_id,
                kind=license_.kind.value,
                status=license_.status.value,
                granted_at=license_.granted_at,
                expires_at=license_.expires_at,
            )
        )
        await self._session.flush()

    async def get_license(self, listing_id: UUID, org_id: TenantId) -> License | None:
        model = (
            await self._session.execute(
                select(MarketplaceLicenseModel).where(
                    MarketplaceLicenseModel.listing_id == listing_id,
                    MarketplaceLicenseModel.licensee_org_id == org_id,
                )
            )
        ).scalars().first()
        if model is None:
            return None
        return License(
            id=model.id,
            listing_id=model.listing_id,
            licensee_org_id=TenantId(model.licensee_org_id),
            kind=LicenseKind(model.kind),
            status=LicenseStatus(model.status),
            granted_at=model.granted_at,
            expires_at=model.expires_at,
        )

    async def list_licenses_for_org(self, org_id: TenantId) -> list[License]:
        rows = (
            await self._session.execute(
                select(MarketplaceLicenseModel)
                .where(MarketplaceLicenseModel.licensee_org_id == org_id)
                .order_by(MarketplaceLicenseModel.granted_at.desc())
            )
        ).scalars().all()
        return [
            License(
                id=m.id,
                listing_id=m.listing_id,
                licensee_org_id=TenantId(m.licensee_org_id),
                kind=LicenseKind(m.kind),
                status=LicenseStatus(m.status),
                granted_at=m.granted_at,
                expires_at=m.expires_at,
            )
            for m in rows
        ]
