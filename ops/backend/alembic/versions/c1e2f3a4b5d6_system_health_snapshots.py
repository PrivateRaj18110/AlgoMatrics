"""system health snapshots

Revision ID: c1e2f3a4b5d6
Revises: b4d8e2a7c9f1
Create Date: 2026-08-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c1e2f3a4b5d6"
down_revision = "b4d8e2a7c9f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_health_snapshots",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("machine_id", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(), nullable=True),
        sa.Column("event_id", sa.String(), nullable=True),
        sa.Column("timestamp_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tick_rate", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("tick_delay_ms", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("queue_size", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("queue_wait_ms", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("avg_latency_ms", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("p95_latency_ms", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("p99_latency_ms", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("api_success_pct", sa.Float(), nullable=False, server_default=sa.text("100.0")),
        sa.Column("signal_fill_rate_pct", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("cpu_usage_pct", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("memory_mb", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'STABLE'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_system_health_snapshots_machine_time",
        "system_health_snapshots",
        ["machine_id", "timestamp_utc"],
        unique=False,
    )
    op.create_index(
        "ix_system_health_snapshots_time",
        "system_health_snapshots",
        ["timestamp_utc"],
        unique=False,
    )
    op.create_index(
        "ix_system_health_snapshots_event_id",
        "system_health_snapshots",
        ["event_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_system_health_snapshots_event_id", table_name="system_health_snapshots")
    op.drop_index("ix_system_health_snapshots_time", table_name="system_health_snapshots")
    op.drop_index("ix_system_health_snapshots_machine_time", table_name="system_health_snapshots")
    op.drop_table("system_health_snapshots")
