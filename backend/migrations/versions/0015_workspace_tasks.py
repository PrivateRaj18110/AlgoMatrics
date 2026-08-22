"""Workspace tasks (to-do list).

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("notes", sa.String(length=2000), nullable=True),
        sa.Column("priority", sa.String(length=10), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tag", sa.String(length=60), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_workspace_tasks"),
    )
    op.create_index(
        "ix_workspace_tasks_org_user",
        "workspace_tasks",
        ["organization_id", "user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_workspace_tasks_org_user", table_name="workspace_tasks")
    op.drop_table("workspace_tasks")
