"""Mobile device registry (push tokens).

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mobile_devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("platform", sa.String(length=10), nullable=False),
        sa.Column("push_token", sa.String(length=4096), nullable=False),
        sa.Column("app_version", sa.String(length=40), nullable=True),
        sa.Column("device_name", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_mobile_devices"),
        sa.UniqueConstraint("push_token", name="uq_mobile_devices_push_token"),
    )
    op.create_index(
        "ix_mobile_devices_org_user",
        "mobile_devices",
        ["organization_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_mobile_devices_org_user", table_name="mobile_devices")
    op.drop_table("mobile_devices")
