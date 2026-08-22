"""phase 3 retention markers

Adds an auditable marker for EOD raw-byte pruning. Metadata and derived quant
reports can then remain visible after raw object bytes are explicitly removed by
the disabled-by-default retention job.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "ad9f3b6c2e41"
down_revision = "f4a9c3d2b8e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("eod_datasets") as batch_op:
        batch_op.add_column(sa.Column("raw_deleted_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index("ix_eod_datasets_raw_deleted_at", ["raw_deleted_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("eod_datasets") as batch_op:
        batch_op.drop_index("ix_eod_datasets_raw_deleted_at")
        batch_op.drop_column("raw_deleted_at")
