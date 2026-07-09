from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from algo_platform.shared.infrastructure.database import Base


class MarketplaceListingModel(Base):
    __tablename__ = "marketplace_listings"
    __table_args__ = (
        Index("ix_marketplace_listings_status", "status"),
        Index("ix_marketplace_listings_publisher", "publisher_org_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    strategy_id: Mapped[uuid.UUID] = mapped_column(index=True)
    publisher_org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(String(120))
    summary: Mapped[str] = mapped_column(String(2000), default="")
    status: Mapped[str] = mapped_column(String(15))
    pricing_model: Mapped[str] = mapped_column(String(15))
    price: Mapped[Decimal] = mapped_column(default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3))
    revenue_share_percent: Mapped[Decimal] = mapped_column(default=Decimal("70"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MarketplaceReviewModel(Base):
    __tablename__ = "marketplace_reviews"
    __table_args__ = (
        UniqueConstraint("listing_id", "reviewer_org_id", name="uq_marketplace_reviews_org"),
        Index("ix_marketplace_reviews_listing", "listing_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    listing_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("marketplace_listings.id", ondelete="CASCADE")
    )
    reviewer_org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str] = mapped_column(String(2000), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MarketplaceLicenseModel(Base):
    __tablename__ = "marketplace_licenses"
    __table_args__ = (
        UniqueConstraint("listing_id", "licensee_org_id", name="uq_marketplace_licenses_org"),
        Index("ix_marketplace_licenses_org", "licensee_org_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    listing_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("marketplace_listings.id", ondelete="CASCADE")
    )
    licensee_org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE")
    )
    kind: Mapped[str] = mapped_column(String(15))
    status: Mapped[str] = mapped_column(String(15))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
