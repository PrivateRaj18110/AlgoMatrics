"""phase 3 quant analytics reports

Stores bounded, derived analytics generated from finalized EOD datasets. Raw
dataset bytes remain in the EOD storage backend.

Revision ID: e9b2c7d5a104
Revises: d8a41f2c9e7b
Create Date: 2026-08-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e9b2c7d5a104"
down_revision: Union[str, None] = "d8a41f2c9e7b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "quant_reports",
        sa.Column("report_id", sa.String(), nullable=False),
        sa.Column("dataset_id", sa.String(), nullable=False),
        sa.Column("machine_id", sa.String(), nullable=False),
        sa.Column("trading_date", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("coverage_json", sa.Text(), nullable=False),
        sa.Column("trade_metrics_json", sa.Text(), nullable=False),
        sa.Column("market_replay_json", sa.Text(), nullable=False),
        sa.Column("warnings_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("report_id"),
    )
    with op.batch_alter_table("quant_reports", schema=None) as batch_op:
        batch_op.create_index("ix_quant_reports_dataset_id", ["dataset_id"], unique=False)
        batch_op.create_index("ix_quant_reports_machine_id", ["machine_id"], unique=False)
        batch_op.create_index("ix_quant_reports_trading_date", ["trading_date"], unique=False)
        batch_op.create_index("ix_quant_reports_created_at", ["created_at"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("quant_reports", schema=None) as batch_op:
        batch_op.drop_index("ix_quant_reports_created_at")
        batch_op.drop_index("ix_quant_reports_trading_date")
        batch_op.drop_index("ix_quant_reports_machine_id")
        batch_op.drop_index("ix_quant_reports_dataset_id")
    op.drop_table("quant_reports")
