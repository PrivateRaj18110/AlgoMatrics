"""phase 3 EOD dataset landing catalog

Tracks end-of-day manifests, upload progress and checksum validation. Raw
dataset bytes live behind the storage port, not in PostgreSQL.

Revision ID: d8a41f2c9e7b
Revises: c0b5f6a7e8d9
Create Date: 2026-08-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d8a41f2c9e7b"
down_revision: Union[str, None] = "c0b5f6a7e8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "eod_datasets",
        sa.Column("dataset_id", sa.String(), nullable=False),
        sa.Column("machine_id", sa.String(), nullable=False),
        sa.Column("machine", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=True),
        sa.Column("trading_date", sa.String(), nullable=False),
        sa.Column("schema_version", sa.String(), nullable=False),
        sa.Column("manifest_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column("storage_backend", sa.String(), nullable=False),
        sa.Column("total_files", sa.Integer(), nullable=False),
        sa.Column("uploaded_files", sa.Integer(), nullable=False),
        sa.Column("total_bytes", sa.BigInteger(), nullable=False),
        sa.Column("uploaded_bytes", sa.BigInteger(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("dataset_id"),
    )
    with op.batch_alter_table("eod_datasets", schema=None) as batch_op:
        batch_op.create_index("ix_eod_datasets_machine_id", ["machine_id"], unique=False)
        batch_op.create_index("ix_eod_datasets_status", ["status"], unique=False)
        batch_op.create_index("ix_eod_datasets_trading_date", ["trading_date"], unique=False)
        batch_op.create_index("ix_eod_datasets_received_at", ["received_at"], unique=False)

    op.create_table(
        "eod_dataset_files",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("dataset_id", sa.String(), nullable=False),
        sa.Column("file_id", sa.String(), nullable=False),
        sa.Column("relative_path", sa.String(), nullable=False),
        sa.Column("dataset_type", sa.String(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("row_count", sa.BigInteger(), nullable=True),
        sa.Column("storage_key", sa.String(), nullable=True),
        sa.Column("bytes_received", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("checksum_status", sa.String(), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "file_id", name="uq_eod_dataset_file_id"),
        sa.UniqueConstraint("dataset_id", "relative_path", name="uq_eod_dataset_relative_path"),
    )
    with op.batch_alter_table("eod_dataset_files", schema=None) as batch_op:
        batch_op.create_index("ix_eod_dataset_files_dataset_id", ["dataset_id"], unique=False)
        batch_op.create_index("ix_eod_dataset_files_status", ["status"], unique=False)
        batch_op.create_index("ix_eod_dataset_files_dataset_type", ["dataset_type"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("eod_dataset_files", schema=None) as batch_op:
        batch_op.drop_index("ix_eod_dataset_files_dataset_type")
        batch_op.drop_index("ix_eod_dataset_files_status")
        batch_op.drop_index("ix_eod_dataset_files_dataset_id")
    op.drop_table("eod_dataset_files")

    with op.batch_alter_table("eod_datasets", schema=None) as batch_op:
        batch_op.drop_index("ix_eod_datasets_received_at")
        batch_op.drop_index("ix_eod_datasets_trading_date")
        batch_op.drop_index("ix_eod_datasets_status")
        batch_op.drop_index("ix_eod_datasets_machine_id")
    op.drop_table("eod_datasets")
