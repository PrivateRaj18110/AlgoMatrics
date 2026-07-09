"""Payment refund tracking.

Adds ``refunded_amount`` to payments so partial and full refunds are recorded
against the original captured payment.

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE payments ADD COLUMN IF NOT EXISTS "
        "refunded_amount NUMERIC(28, 10) NOT NULL DEFAULT 0"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE payments DROP COLUMN IF EXISTS refunded_amount")
