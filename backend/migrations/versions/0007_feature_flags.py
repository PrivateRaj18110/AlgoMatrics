"""Enterprise feature flags.

Creates the runtime-configurable feature-flag tables and seeds the platform's
known flags (marketplace, AI, paper/live trading, and per-broker gates).

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (key, description, enabled) — seeded once; safe to re-run (ON CONFLICT DO NOTHING).
_SEED_FLAGS: tuple[tuple[str, str, bool], ...] = (
    ("marketplace", "Strategy marketplace", False),
    ("ai", "AI trading assistant and analytics", False),
    ("paper_trading", "Paper trading", True),
    ("live_trading", "Live trading", False),
    ("broker.paper", "Paper broker", True),
    ("broker.zerodha", "Zerodha broker", False),
    ("broker.angelone", "Angel One broker", False),
    ("broker.delta", "Delta broker", False),
    ("broker.binance", "Binance broker", False),
    ("broker.interactive_brokers", "Interactive Brokers", False),
    ("broker.mt5", "MetaTrader 5 broker", False),
)


def upgrade() -> None:
    op.create_table(
        "feature_flags",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("kill_switch", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("rollout_percentage", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("key", name="pk_feature_flags"),
    )
    op.create_table(
        "feature_flag_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("flag_key", sa.String(length=80), nullable=False),
        sa.Column("scope_type", sa.String(length=20), nullable=False),
        sa.Column("scope_id", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["flag_key"],
            ["feature_flags.key"],
            name="fk_feature_flag_overrides_flag_key_feature_flags",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_feature_flag_overrides"),
        sa.UniqueConstraint(
            "flag_key", "scope_type", "scope_id", name="uq_feature_flag_overrides_scope"
        ),
    )
    op.create_index(
        "ix_feature_flag_overrides_flag_key", "feature_flag_overrides", ["flag_key"]
    )

    for key, description, enabled in _SEED_FLAGS:
        op.execute(
            sa.text(
                "INSERT INTO feature_flags (key, description, enabled) "
                "VALUES (:key, :description, :enabled) ON CONFLICT (key) DO NOTHING"
            ).bindparams(key=key, description=description, enabled=enabled)
        )


def downgrade() -> None:
    op.drop_index(
        "ix_feature_flag_overrides_flag_key", table_name="feature_flag_overrides"
    )
    op.drop_table("feature_flag_overrides")
    op.drop_table("feature_flags")
