"""Add recurring billing provider state and webhook receipts.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # IF NOT EXISTS keeps fresh installs compatible with the historical
    # metadata-driven baseline while still upgrading databases created at 0002.
    op.execute(
        "ALTER TABLE plans ADD COLUMN IF NOT EXISTS "
        "provider_prices JSONB NOT NULL DEFAULT '{}'::jsonb"
    )
    op.execute(
        "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS "
        "provider_customer_id VARCHAR(120)"
    )
    op.execute(
        "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS "
        "provider_price_ref VARCHAR(120)"
    )
    op.execute(
        "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS "
        "provider_status VARCHAR(30)"
    )
    op.execute(
        "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS "
        "last_provider_event_at TIMESTAMPTZ"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_subscriptions_provider_ref "
        "ON subscriptions (provider, provider_ref) WHERE provider_ref IS NOT NULL"
    )
    op.create_table(
        "billing_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("provider_event_id", sa.String(length=160), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="processing",
        ),
        sa.Column("error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_billing_webhook_events"),
        sa.UniqueConstraint(
            "provider",
            "provider_event_id",
            name="uq_billing_webhook_events_provider_provider_event_id",
        ),
    )
    op.create_index(
        "ix_billing_webhook_events_created",
        "billing_webhook_events",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_billing_webhook_events_created", table_name="billing_webhook_events")
    op.drop_table("billing_webhook_events")
    op.execute("DROP INDEX IF EXISTS ix_subscriptions_provider_ref")
    op.drop_column("subscriptions", "last_provider_event_at")
    op.drop_column("subscriptions", "provider_status")
    op.drop_column("subscriptions", "provider_price_ref")
    op.drop_column("subscriptions", "provider_customer_id")
    op.drop_column("plans", "provider_prices")
