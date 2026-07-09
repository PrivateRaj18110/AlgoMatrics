"""Invoice tax (GST) columns.

Adds ``tax`` and ``tax_rate`` to invoices so tax is stored alongside the subtotal
and discount. Existing rows default to zero tax.

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS tax NUMERIC(28, 10) NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE invoices ADD COLUMN IF NOT EXISTS tax_rate NUMERIC(28, 10) NOT NULL DEFAULT 0"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE invoices DROP COLUMN IF EXISTS tax_rate")
    op.execute("ALTER TABLE invoices DROP COLUMN IF EXISTS tax")
