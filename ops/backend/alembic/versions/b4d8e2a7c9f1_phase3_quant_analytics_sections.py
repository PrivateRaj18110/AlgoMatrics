"""phase 3 quant analytics sections

Stores explicit read-only analytics availability sections beside the existing
trade metrics and replay report. The sections distinguish available,
not-available and insufficient-data metrics instead of inventing numbers.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b4d8e2a7c9f1"
down_revision = "ad9f3b6c2e41"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("quant_reports") as batch_op:
        batch_op.add_column(
            sa.Column(
                "analytics_json",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("quant_reports") as batch_op:
        batch_op.drop_column("analytics_json")
