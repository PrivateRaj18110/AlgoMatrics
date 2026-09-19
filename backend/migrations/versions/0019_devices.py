"""Trading devices and the events they report.

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("key_prefix", sa.String(length=16), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_ip", sa.String(length=45), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("health", postgresql.JSONB(), nullable=True),
        sa.Column("positions", postgresql.JSONB(), nullable=True),
        sa.Column("positions_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_devices"),
        sa.UniqueConstraint("key_hash", name="uq_devices_key_hash"),
    )
    op.create_index("ix_devices_org", "devices", ["organization_id"])
    op.create_table(
        "device_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_device_events"),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.id"],
            name="fk_device_events_device_id_devices",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_device_events_device_time", "device_events", ["device_id", "occurred_at"])
    op.create_index(
        "ix_device_events_org_time", "device_events", ["organization_id", "occurred_at"]
    )


def downgrade() -> None:
    op.drop_table("device_events")
    op.drop_table("devices")
