"""phase 3 machine status and event timeline metadata

Adds bounded current-state fields to ``machines`` and safe, filterable metadata
to ``events``. Raw telemetry payloads are intentionally not stored here.

Revision ID: c0b5f6a7e8d9
Revises: b7c2e4a91f30
Create Date: 2026-08-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c0b5f6a7e8d9"
down_revision: Union[str, None] = "b7c2e4a91f30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("machines", schema=None) as batch_op:
        batch_op.add_column(sa.Column("agent_version", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("hostname", sa.String(), server_default="", nullable=False))
        batch_op.add_column(sa.Column("environment", sa.String(), server_default="", nullable=False))
        batch_op.add_column(sa.Column("last_event", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("last_trade", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("last_error", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("last_successful_upload", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("queue_depth", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("oldest_pending_age_sec", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("transport_state", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("current_session_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("trading_process_state", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("last_eod_sync", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("last_eod_status", sa.String(), nullable=True))
        batch_op.create_index("ix_machines_current_session_id", ["current_session_id"], unique=False)
        batch_op.create_index(
            "ix_machines_last_successful_upload", ["last_successful_upload"], unique=False
        )

    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.add_column(sa.Column("event_type", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("strategy", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("symbol", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("session_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("sequence_id", sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column("payload_summary", sa.Text(), nullable=True))
        batch_op.create_index("ix_events_event_type_time", ["event_type", "time"], unique=False)
        batch_op.create_index("ix_events_session_id", ["session_id"], unique=False)
        batch_op.create_index("ix_events_strategy", ["strategy"], unique=False)
        batch_op.create_index("ix_events_symbol", ["symbol"], unique=False)
        batch_op.create_index("ix_events_severity_time", ["severity", "time"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.drop_index("ix_events_severity_time")
        batch_op.drop_index("ix_events_symbol")
        batch_op.drop_index("ix_events_strategy")
        batch_op.drop_index("ix_events_session_id")
        batch_op.drop_index("ix_events_event_type_time")
        batch_op.drop_column("payload_summary")
        batch_op.drop_column("sequence_id")
        batch_op.drop_column("session_id")
        batch_op.drop_column("symbol")
        batch_op.drop_column("strategy")
        batch_op.drop_column("event_type")

    with op.batch_alter_table("machines", schema=None) as batch_op:
        batch_op.drop_index("ix_machines_last_successful_upload")
        batch_op.drop_index("ix_machines_current_session_id")
        batch_op.drop_column("last_eod_status")
        batch_op.drop_column("last_eod_sync")
        batch_op.drop_column("trading_process_state")
        batch_op.drop_column("current_session_id")
        batch_op.drop_column("transport_state")
        batch_op.drop_column("oldest_pending_age_sec")
        batch_op.drop_column("queue_depth")
        batch_op.drop_column("last_successful_upload")
        batch_op.drop_column("last_error")
        batch_op.drop_column("last_trade")
        batch_op.drop_column("last_event")
        batch_op.drop_column("environment")
        batch_op.drop_column("hostname")
        batch_op.drop_column("agent_version")
