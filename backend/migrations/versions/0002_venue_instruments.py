"""Add broker-specific venue instrument mappings.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "venue_instruments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("broker_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("instrument_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("venue_symbol", sa.String(length=80), nullable=False),
        sa.Column("exchange", sa.String(length=30), nullable=False),
        sa.Column("instrument_token", sa.String(length=120), nullable=True),
        sa.Column("tick_size", sa.Numeric(28, 10), nullable=False),
        sa.Column("lot_size", sa.Numeric(28, 10), nullable=False),
        sa.Column(
            "contract_multiplier",
            sa.Numeric(28, 10),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "venue_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["broker_id"],
            ["brokers.id"],
            name="fk_venue_instruments_broker_id_brokers",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name="fk_venue_instruments_instrument_id_instruments",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_venue_instruments"),
        sa.UniqueConstraint(
            "broker_id",
            "instrument_id",
            name="uq_venue_instruments_broker_id_instrument_id",
        ),
        sa.UniqueConstraint(
            "broker_id",
            "exchange",
            "venue_symbol",
            name="uq_venue_instruments_broker_id_exchange_venue_symbol",
        ),
        sa.CheckConstraint(
            "tick_size > 0 AND lot_size > 0 AND contract_multiplier > 0",
            name="positive_sizes",
        ),
    )
    op.create_index(
        "ix_venue_instruments_broker_active",
        "venue_instruments",
        ["broker_id", "is_active"],
    )
    op.create_index(
        "ix_venue_instruments_instrument",
        "venue_instruments",
        ["instrument_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_venue_instruments_instrument", table_name="venue_instruments")
    op.drop_index("ix_venue_instruments_broker_active", table_name="venue_instruments")
    op.drop_table("venue_instruments")
