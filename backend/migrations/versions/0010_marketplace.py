"""Strategy marketplace: listings, reviews, and licenses.

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "marketplace_listings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("publisher_org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("summary", sa.String(length=2000), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=15), nullable=False),
        sa.Column("pricing_model", sa.String(length=15), nullable=False),
        sa.Column("price", sa.Numeric(28, 10), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("revenue_share_percent", sa.Numeric(28, 10), nullable=False, server_default="70"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["publisher_org_id"],
            ["organizations.id"],
            name="fk_marketplace_listings_publisher_org_id_organizations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_marketplace_listings"),
    )
    op.create_index("ix_marketplace_listings_strategy_id", "marketplace_listings", ["strategy_id"])
    op.create_index("ix_marketplace_listings_status", "marketplace_listings", ["status"])
    op.create_index(
        "ix_marketplace_listings_publisher", "marketplace_listings", ["publisher_org_id"]
    )

    op.create_table(
        "marketplace_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("comment", sa.String(length=2000), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["marketplace_listings.id"],
            name="fk_marketplace_reviews_listing_id_marketplace_listings",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_org_id"],
            ["organizations.id"],
            name="fk_marketplace_reviews_reviewer_org_id_organizations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_marketplace_reviews"),
        sa.UniqueConstraint("listing_id", "reviewer_org_id", name="uq_marketplace_reviews_org"),
    )
    op.create_index("ix_marketplace_reviews_listing", "marketplace_reviews", ["listing_id"])

    op.create_table(
        "marketplace_licenses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("licensee_org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=15), nullable=False),
        sa.Column("status", sa.String(length=15), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["marketplace_listings.id"],
            name="fk_marketplace_licenses_listing_id_marketplace_listings",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["licensee_org_id"],
            ["organizations.id"],
            name="fk_marketplace_licenses_licensee_org_id_organizations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_marketplace_licenses"),
        sa.UniqueConstraint("listing_id", "licensee_org_id", name="uq_marketplace_licenses_org"),
    )
    op.create_index("ix_marketplace_licenses_org", "marketplace_licenses", ["licensee_org_id"])


def downgrade() -> None:
    op.drop_table("marketplace_licenses")
    op.drop_table("marketplace_reviews")
    op.drop_table("marketplace_listings")
