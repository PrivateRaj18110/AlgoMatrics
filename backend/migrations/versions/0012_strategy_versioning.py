"""Strategy version approvals and deployment history.

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "strategy_version_approvals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("submitted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("review_note", sa.String(length=1000), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["strategy_versions.id"],
            name="fk_strategy_version_approvals_version_id_strategy_versions",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_strategy_version_approvals"),
        sa.UniqueConstraint("version_id", name="uq_strategy_version_approvals_version"),
    )
    op.create_index(
        "ix_strategy_version_approvals_org",
        "strategy_version_approvals",
        ["organization_id", "status"],
    )

    op.create_table(
        "strategy_deployments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_label", sa.String(length=20), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False, server_default="deploy"),
        sa.Column("deployed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("deployed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["strategies.id"],
            name="fk_strategy_deployments_strategy_id_strategies",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_strategy_deployments"),
    )
    op.create_index(
        "ix_strategy_deployments_strategy",
        "strategy_deployments",
        ["strategy_id", "deployed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_strategy_deployments_strategy", table_name="strategy_deployments")
    op.drop_table("strategy_deployments")
    op.drop_index(
        "ix_strategy_version_approvals_org", table_name="strategy_version_approvals"
    )
    op.drop_table("strategy_version_approvals")
