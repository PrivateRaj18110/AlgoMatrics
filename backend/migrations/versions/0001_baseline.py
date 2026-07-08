"""Baseline schema: full platform tables, constraints, and sequences.

Revision ID: 0001
Revises:
Create Date: 2026-07-04

The baseline creates every table from the shared declarative metadata so the
models and schema cannot drift at bootstrap. Subsequent revisions must use
explicit, incremental DDL (expand/migrate/contract in production).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Import model modules so Base.metadata carries every table.
import algo_platform.modules.audit.infrastructure.models
import algo_platform.modules.billing.infrastructure.models
import algo_platform.modules.brokerage.infrastructure.models
import algo_platform.modules.identity.infrastructure.models
import algo_platform.modules.instruments.infrastructure.models
import algo_platform.modules.notifications.infrastructure.models
import algo_platform.modules.organizations.infrastructure.models
import algo_platform.modules.portfolio.infrastructure.models
import algo_platform.modules.risk.infrastructure.models
import algo_platform.modules.strategies.infrastructure.models
import algo_platform.modules.trading.infrastructure.models
import algo_platform.shared.infrastructure.email_outbox
import algo_platform.shared.infrastructure.outbox  # noqa: F401
from algo_platform.shared.infrastructure.database import Base

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    op.execute(sa.text("CREATE SEQUENCE IF NOT EXISTS invoice_number_seq START 1"))
    # This historical baseline intentionally excludes tables introduced by
    # later revisions. Because the original baseline was metadata-driven,
    # failing to pin this list would make a fresh install create future tables
    # before their explicit Alembic migrations run.
    later_revision_tables = {
        "venue_instruments",
        "billing_webhook_events",
        "email_outbox",
        "notification_reads",
        "feature_flags",
        "feature_flag_overrides",
    }
    baseline_tables = [
        table for table in Base.metadata.sorted_tables if table.name not in later_revision_tables
    ]
    Base.metadata.create_all(bind=bind, tables=baseline_tables)
    # Business-rule check constraints not expressible in the ORM mappings.
    op.execute(
        sa.text(
            "ALTER TABLE orders ADD CONSTRAINT ck_orders_positive_quantity CHECK (quantity > 0)"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE orders ADD CONSTRAINT ck_orders_fill_bounds "
            "CHECK (filled_quantity >= 0 AND filled_quantity <= quantity)"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE executions ADD CONSTRAINT ck_executions_positive "
            "CHECK (quantity > 0 AND price > 0 AND fee >= 0)"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE plans ADD CONSTRAINT ck_plans_prices_non_negative "
            "CHECK (price_monthly >= 0 AND price_yearly >= 0)"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE invoices ADD CONSTRAINT ck_invoices_amounts "
            "CHECK (subtotal >= 0 AND discount >= 0 AND total >= 0)"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
    op.execute(sa.text("DROP SEQUENCE IF EXISTS invoice_number_seq"))
