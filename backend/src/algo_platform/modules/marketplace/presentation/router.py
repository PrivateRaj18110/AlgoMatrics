"""Marketplace HTTP API. Gated by the ``marketplace`` feature flag."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from algo_platform.api.dependencies.core import SessionDep
from algo_platform.api.dependencies.pagination import PageDep
from algo_platform.api.dependencies.tenant import TenantContext, TenantDep, require_permission
from algo_platform.modules.feature_flags.presentation.dependencies import require_feature
from algo_platform.modules.marketplace.application.service import MarketplaceService
from algo_platform.modules.marketplace.domain.marketplace import PricingModel
from algo_platform.modules.organizations.domain.roles import Permission
from algo_platform.modules.strategies.application.directory import StrategyDirectory
from algo_platform.shared.domain.errors import NotFoundError

router = APIRouter(
    prefix="/marketplace",
    tags=["marketplace"],
    dependencies=[Depends(require_feature("marketplace"))],
)

ManageDep = Annotated[TenantContext, Depends(require_permission(Permission.STRATEGIES_MANAGE))]


class PublishRequest(BaseModel):
    strategy_id: UUID
    title: str = Field(min_length=3, max_length=120)
    summary: str = Field(default="", max_length=2000)
    pricing_model: PricingModel
    price: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    revenue_share_percent: Decimal = Field(default=Decimal("70"), ge=0, le=100)


class ListingResponse(BaseModel):
    id: UUID
    strategy_id: UUID
    title: str
    summary: str
    status: str
    pricing_model: str
    price: Decimal
    currency: str
    revenue_share_percent: Decimal
    review_count: int
    average_rating: float
    license_count: int


class ReviewRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=2000)


class ReviewResponse(BaseModel):
    reviewer_org_id: UUID
    rating: int
    comment: str
    created_at: datetime


class LicenseResponse(BaseModel):
    id: UUID
    listing_id: UUID
    kind: str
    status: str
    granted_at: datetime
    expires_at: datetime | None


class RevenueResponse(BaseModel):
    currency: str
    gross: Decimal
    publisher_earnings: Decimal
    platform_fee: Decimal
    license_count: int


def _listing_response(view: object) -> ListingResponse:
    listing = view.listing  # type: ignore[attr-defined]
    stats = view.stats  # type: ignore[attr-defined]
    return ListingResponse(
        id=listing.id,
        strategy_id=listing.strategy_id,
        title=listing.title,
        summary=listing.summary,
        status=listing.status.value,
        pricing_model=listing.pricing_model.value,
        price=listing.price,
        currency=listing.currency,
        revenue_share_percent=listing.revenue_share_percent,
        review_count=stats.review_count,
        average_rating=stats.average_rating,
        license_count=stats.license_count,
    )


@router.post("/listings", response_model=ListingResponse, status_code=201)
async def publish_listing(
    payload: PublishRequest, tenant: ManageDep, session: SessionDep
) -> ListingResponse:
    # Ownership check: the caller must own the strategy being listed.
    if not await StrategyDirectory(session).owns(tenant.organization_id, payload.strategy_id):
        raise NotFoundError("strategy not found")
    service = MarketplaceService(session)
    listing = await service.publish(
        publisher_org_id=tenant.organization_id,
        strategy_id=payload.strategy_id,
        title=payload.title,
        summary=payload.summary,
        pricing_model=payload.pricing_model,
        price=payload.price,
        currency=payload.currency,
        revenue_share_percent=payload.revenue_share_percent,
    )
    view, _ = await service.detail(listing.id)
    return _listing_response(view)


@router.get("/listings", response_model=list[ListingResponse])
async def browse_listings(
    tenant: TenantDep, session: SessionDep, page: PageDep
) -> list[ListingResponse]:
    views = await MarketplaceService(session).browse(limit=page.limit, offset=page.offset)
    return [_listing_response(v) for v in views]


@router.get("/listings/{listing_id}", response_model=ListingResponse)
async def listing_detail(
    listing_id: UUID, tenant: TenantDep, session: SessionDep
) -> ListingResponse:
    view, _reviews = await MarketplaceService(session).detail(listing_id)
    return _listing_response(view)


@router.get("/listings/{listing_id}/reviews", response_model=list[ReviewResponse])
async def listing_reviews(
    listing_id: UUID, tenant: TenantDep, session: SessionDep
) -> list[ReviewResponse]:
    _view, reviews = await MarketplaceService(session).detail(listing_id)
    return [
        ReviewResponse(
            reviewer_org_id=r.reviewer_org_id,
            rating=r.rating,
            comment=r.comment,
            created_at=r.created_at,
        )
        for r in reviews
    ]


@router.post("/listings/{listing_id}/unlist", status_code=204)
async def unlist_listing(listing_id: UUID, tenant: ManageDep, session: SessionDep) -> None:
    await MarketplaceService(session).unlist(listing_id, tenant.organization_id)


@router.post("/listings/{listing_id}/license", response_model=LicenseResponse, status_code=201)
async def acquire_license(
    listing_id: UUID, tenant: TenantDep, session: SessionDep
) -> LicenseResponse:
    license_ = await MarketplaceService(session).acquire_license(
        listing_id, tenant.organization_id
    )
    return LicenseResponse(
        id=license_.id,
        listing_id=license_.listing_id,
        kind=license_.kind.value,
        status=license_.status.value,
        granted_at=license_.granted_at,
        expires_at=license_.expires_at,
    )


@router.post("/listings/{listing_id}/reviews", response_model=ReviewResponse, status_code=201)
async def create_review(
    listing_id: UUID, payload: ReviewRequest, tenant: TenantDep, session: SessionDep
) -> ReviewResponse:
    review = await MarketplaceService(session).review(
        listing_id, tenant.organization_id, rating=payload.rating, comment=payload.comment
    )
    return ReviewResponse(
        reviewer_org_id=review.reviewer_org_id,
        rating=review.rating,
        comment=review.comment,
        created_at=review.created_at,
    )


@router.get("/licenses", response_model=list[LicenseResponse])
async def my_licenses(tenant: TenantDep, session: SessionDep) -> list[LicenseResponse]:
    licenses = await MarketplaceService(session).my_licenses(tenant.organization_id)
    return [
        LicenseResponse(
            id=lic.id,
            listing_id=lic.listing_id,
            kind=lic.kind.value,
            status=lic.status.value,
            granted_at=lic.granted_at,
            expires_at=lic.expires_at,
        )
        for lic in licenses
    ]


@router.get("/revenue", response_model=list[RevenueResponse])
async def revenue(tenant: ManageDep, session: SessionDep) -> list[RevenueResponse]:
    reports = await MarketplaceService(session).revenue_report(tenant.organization_id)
    return [
        RevenueResponse(
            currency=r.currency,
            gross=r.gross,
            publisher_earnings=r.publisher_earnings,
            platform_fee=r.platform_fee,
            license_count=r.license_count,
        )
        for r in reports
    ]
