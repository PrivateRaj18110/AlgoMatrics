"""monitoring.v1 receiver — evidence, quarantine, conflicts, sequence, projections

Purely additive: seven new tables, no change to any existing one. The
``raj_monitor`` agent path is untouched and keeps its own tables, so this
migration can be applied to a running deployment and rolled back without
touching agent telemetry.

``downgrade`` drops only what ``upgrade`` created. Note that dropping
``monitoring_evidence`` destroys received evidence — a downgrade is therefore a
data-losing operation for monitoring.v1 specifically, and should be preceded by
a backup. Everything except evidence is derived and safe to lose.

Revision ID: a3c7e1d94b62
Revises: c1e2f3a4b5d6
Create Date: 2026-09-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a3c7e1d94b62"
down_revision = "c1e2f3a4b5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Immutable received evidence -------------------------------------
    op.create_table(
        "monitoring_evidence",
        sa.Column("message_id", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("source_instance", sa.String(length=128), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", sa.String(length=256), nullable=True),
        sa.Column("supersedes", sa.String(length=64), nullable=True),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("runtime", sa.String(length=16), nullable=False),
        sa.Column("environment", sa.String(length=16), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("compatibility", sa.String(length=256), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data_as_of", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stale_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("freshness_state", sa.String(length=16), nullable=True),
        sa.Column("trust_level", sa.String(length=16), nullable=True),
        sa.Column("capture_id", sa.String(length=128), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("envelope_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("message_id"),
    )
    op.create_index(
        "ix_monitoring_evidence_source_seq",
        "monitoring_evidence",
        ["source_id", "source_instance", "sequence"],
    )
    op.create_index(
        "ix_monitoring_evidence_entity",
        "monitoring_evidence",
        ["entity_type", "entity_id", "revision"],
    )
    op.create_index(
        "ix_monitoring_evidence_kind_env",
        "monitoring_evidence",
        ["environment", "kind", "data_as_of"],
    )
    op.create_index("ix_monitoring_evidence_received_at", "monitoring_evidence", ["received_at"])

    # --- Preserved request bytes (quarantine forensics only) --------------
    op.create_table(
        "monitoring_raw_requests",
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("claimed_source_id", sa.String(length=128), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_encoding", sa.String(length=32), nullable=True),
        sa.Column("byte_length", sa.Integer(), nullable=False),
        sa.Column("body_sha256", sa.String(length=64), nullable=False),
        sa.Column("body", sa.LargeBinary(), nullable=False),
        sa.PrimaryKeyConstraint("request_id"),
    )
    op.create_index(
        "ix_monitoring_raw_requests_received_at", "monitoring_raw_requests", ["received_at"]
    )

    # --- Quarantine (distinct from ingest_dead_letters) -------------------
    op.create_table(
        "monitoring_quarantine",
        sa.Column("quarantine_id", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("batch_index", sa.Integer(), nullable=True),
        sa.Column("message_id", sa.String(length=64), nullable=True),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=True),
        sa.Column("environment", sa.String(length=16), nullable=True),
        sa.Column("reason", sa.String(length=128), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("integrity_algorithm", sa.String(length=32), nullable=True),
        sa.Column("integrity_digest", sa.String(length=128), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("quarantine_id"),
    )
    op.create_index(
        "ix_monitoring_quarantine_received_at", "monitoring_quarantine", ["received_at"]
    )
    op.create_index(
        "ix_monitoring_quarantine_source", "monitoring_quarantine", ["source_id", "reason"]
    )
    op.create_index("ix_monitoring_quarantine_request", "monitoring_quarantine", ["request_id"])

    # --- Conflicts --------------------------------------------------------
    op.create_table(
        "monitoring_conflicts",
        sa.Column("conflict_id", sa.String(length=64), nullable=False),
        sa.Column("environment", sa.String(length=16), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=256), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("existing_message_id", sa.String(length=64), nullable=False),
        sa.Column("incoming_message_id", sa.String(length=64), nullable=False),
        sa.Column("existing_content_hash", sa.String(length=64), nullable=False),
        sa.Column("incoming_content_hash", sa.String(length=64), nullable=False),
        sa.Column("existing_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("incoming_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("conflict_id"),
    )
    op.create_index(
        "ix_monitoring_conflicts_entity",
        "monitoring_conflicts",
        ["entity_type", "entity_id", "revision"],
    )
    op.create_index("ix_monitoring_conflicts_detected_at", "monitoring_conflicts", ["detected_at"])

    # --- Sequence / loss detection ---------------------------------------
    op.create_table(
        "monitoring_sequence_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("source_instance", sa.String(length=128), nullable=False),
        sa.Column("first_sequence", sa.BigInteger(), nullable=False),
        sa.Column("last_sequence", sa.BigInteger(), nullable=False),
        sa.Column("received_count", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("duplicate_count", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "out_of_order_count", sa.BigInteger(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("gap_count", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("missing_ranges", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "source_instance", name="uq_monitoring_sequence_instance"),
    )
    op.create_index(
        "ix_monitoring_sequence_last_seen", "monitoring_sequence_state", ["last_seen_at"]
    )

    # --- Derived projections (safe to drop and rebuild) -------------------
    op.create_table(
        "monitoring_projections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("environment", sa.String(length=16), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("entity_key", sa.String(length=512), nullable=False),
        sa.Column("message_id", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("source_instance", sa.String(length=128), nullable=False),
        sa.Column("runtime", sa.String(length=16), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data_as_of", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stale_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("freshness_state", sa.String(length=16), nullable=True),
        sa.Column("trust_level", sa.String(length=16), nullable=True),
        sa.Column("schema_version", sa.String(length=16), nullable=False),
        sa.Column("observation_json", sa.Text(), nullable=False),
        sa.Column("has_conflict", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "environment",
            "source_id",
            "kind",
            "entity_key",
            name="uq_monitoring_projection_key",
        ),
    )
    op.create_index(
        "ix_monitoring_projection_kind", "monitoring_projections", ["environment", "kind"]
    )
    op.create_index(
        "ix_monitoring_projection_stale_after", "monitoring_projections", ["stale_after"]
    )

    # --- Receiver-side security audit ------------------------------------
    op.create_table(
        "monitoring_audit",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("remote_addr", sa.String(length=64), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_monitoring_audit_at", "monitoring_audit", ["at"])
    op.create_index("ix_monitoring_audit_action", "monitoring_audit", ["action", "outcome"])


def downgrade() -> None:
    op.drop_index("ix_monitoring_audit_action", table_name="monitoring_audit")
    op.drop_index("ix_monitoring_audit_at", table_name="monitoring_audit")
    op.drop_table("monitoring_audit")

    op.drop_index("ix_monitoring_projection_stale_after", table_name="monitoring_projections")
    op.drop_index("ix_monitoring_projection_kind", table_name="monitoring_projections")
    op.drop_table("monitoring_projections")

    op.drop_index("ix_monitoring_sequence_last_seen", table_name="monitoring_sequence_state")
    op.drop_table("monitoring_sequence_state")

    op.drop_index("ix_monitoring_conflicts_detected_at", table_name="monitoring_conflicts")
    op.drop_index("ix_monitoring_conflicts_entity", table_name="monitoring_conflicts")
    op.drop_table("monitoring_conflicts")

    op.drop_index("ix_monitoring_quarantine_request", table_name="monitoring_quarantine")
    op.drop_index("ix_monitoring_quarantine_source", table_name="monitoring_quarantine")
    op.drop_index("ix_monitoring_quarantine_received_at", table_name="monitoring_quarantine")
    op.drop_table("monitoring_quarantine")

    op.drop_index("ix_monitoring_raw_requests_received_at", table_name="monitoring_raw_requests")
    op.drop_table("monitoring_raw_requests")

    op.drop_index("ix_monitoring_evidence_received_at", table_name="monitoring_evidence")
    op.drop_index("ix_monitoring_evidence_kind_env", table_name="monitoring_evidence")
    op.drop_index("ix_monitoring_evidence_entity", table_name="monitoring_evidence")
    op.drop_index("ix_monitoring_evidence_source_seq", table_name="monitoring_evidence")
    op.drop_table("monitoring_evidence")
