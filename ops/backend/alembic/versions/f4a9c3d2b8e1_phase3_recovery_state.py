"""phase 3 recovery current-state fields

Adds bounded recovery fields to machines. Historical recovery events remain in
the event timeline; these columns only hold the latest machine-level recovery
snapshot for fast dashboard reads.

Revision ID: f4a9c3d2b8e1
Revises: e9b2c7d5a104
Create Date: 2026-08-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f4a9c3d2b8e1"
down_revision: Union[str, None] = "e9b2c7d5a104"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("machines", schema=None) as batch_op:
        batch_op.add_column(sa.Column("recovery_state", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("last_recovery_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("events_recovered", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("eod_backlog", sa.Integer(), nullable=True))
        batch_op.create_index("ix_machines_recovery_state", ["recovery_state"], unique=False)
        batch_op.create_index("ix_machines_last_recovery_at", ["last_recovery_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("machines", schema=None) as batch_op:
        batch_op.drop_index("ix_machines_last_recovery_at")
        batch_op.drop_index("ix_machines_recovery_state")
        batch_op.drop_column("eod_backlog")
        batch_op.drop_column("events_recovered")
        batch_op.drop_column("last_recovery_at")
        batch_op.drop_column("recovery_state")
