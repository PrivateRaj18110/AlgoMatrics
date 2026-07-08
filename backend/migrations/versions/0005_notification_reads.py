"""Add per-user read receipts for broadcast notifications.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_reads",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["notification_id"],
            ["notifications.id"],
            name="fk_notification_reads_notification_id_notifications",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_notification_reads"),
        sa.UniqueConstraint(
            "notification_id",
            "user_id",
            name="uq_notification_reads_notification_id_user_id",
        ),
    )
    op.create_index(
        "ix_notification_reads_user",
        "notification_reads",
        ["user_id", "read_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notification_reads_user", table_name="notification_reads")
    op.drop_table("notification_reads")
