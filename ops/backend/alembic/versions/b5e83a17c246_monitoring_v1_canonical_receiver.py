"""monitoring.v1 canonical receiver — reshape storage to the LLS envelope

The previous revision (a3c7e1d94b62) created tables shaped around
``monitoring-export/v1``, a receiver-side proposal that was retired when the
canonical LLS contract arrived. Those tables cannot hold a monitoring.v1 message:
there is no ``observation``, ``source_sequence`` is a string not an integer,
``runtime`` is an array not an enum, and ``stale_after`` does not exist at all.

This revision drops and recreates them. That is safe here and would not be
safe later:

* the a3c7e1d94b62 tables were **never deployed** and have never held a message —
  the ingress that would have written them returned 503 from the moment the
  contract was superseded
* once this receiver is in staging, evidence becomes irreplaceable and any
  future reshaping must migrate rows rather than drop them

``downgrade`` restores the previous shape structurally. It cannot restore rows,
because the two shapes hold different information — but there are no rows to
restore.

Also drops ``monitoring_conflicts``. Under monitoring.v1 ``message_id`` is a
content address, so a changed body cannot keep a valid identity: an identity
collision is caught at validation and quarantined, and a separate conflict table
has nothing left to record.

Revision ID: b5e83a17c246
Revises: a3c7e1d94b62
Create Date: 2026-09-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b5e83a17c246"
down_revision = "a3c7e1d94b62"
branch_labels = None
depends_on = None

_LEGACY_TABLES = (
    "monitoring_projections",
    "monitoring_conflicts",
    "monitoring_quarantine",
    "monitoring_raw_requests",
    "monitoring_sequence_state",
    "monitoring_audit",
    "monitoring_evidence",
)


def upgrade() -> None:
    for table in _LEGACY_TABLES:
        op.drop_table(table)

    # --- Immutable evidence, shaped to the LLS envelope -------------------
    op.create_table(
        "monitoring_evidence",
        sa.Column("message_id", sa.String(length=80), nullable=False),
        sa.Column("source_id", sa.String(length=80), nullable=False),
        sa.Column("source_instance", sa.String(length=80), nullable=False),
        # Verbatim wire value; the ACK must echo it unchanged.
        sa.Column("source_sequence", sa.String(length=24), nullable=False),
        sa.Column("sequence_ordinal", sa.BigInteger(), nullable=False),
        sa.Column("message_type", sa.String(length=48), nullable=False),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        # Two distinct environments, never derived from one another.
        sa.Column("source_environment", sa.String(length=32), nullable=False),
        sa.Column(
            "receiver_deployment_environment",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'UNKNOWN'"),
        ),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_as_of_json", sa.Text(), nullable=False),
        sa.Column("coverage_json", sa.Text(), nullable=False),
        sa.Column("freshness_json", sa.Text(), nullable=False),
        sa.Column("trust_json", sa.Text(), nullable=False),
        sa.Column("runtime_json", sa.Text(), nullable=False),
        sa.Column("freshness_source", sa.String(length=32), nullable=True),
        sa.Column("trust_status", sa.String(length=32), nullable=True),
        sa.Column("coverage_status", sa.String(length=32), nullable=True),
        sa.Column("capture_ref", sa.String(length=160), nullable=True),
        sa.Column("request_sha256", sa.String(length=64), nullable=False),
        sa.Column("message_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("message_id"),
    )
    op.create_index(
        "ix_mon_evidence_instance_seq",
        "monitoring_evidence",
        ["source_id", "source_instance", "sequence_ordinal"],
    )
    op.create_index("ix_mon_evidence_type", "monitoring_evidence", ["message_type", "generated_at"])
    op.create_index("ix_mon_evidence_received_at", "monitoring_evidence", ["received_at"])
    op.create_index("ix_mon_evidence_capture", "monitoring_evidence", ["capture_ref"])

    # --- Ordered-acceptance state ----------------------------------------
    op.create_table(
        "monitoring_sequence_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.String(length=80), nullable=False),
        sa.Column("source_instance", sa.String(length=80), nullable=False),
        sa.Column("last_accepted_sequence", sa.BigInteger(), nullable=False),
        sa.Column("last_accepted_message_id", sa.String(length=80), nullable=False),
        sa.Column("accepted_count", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("duplicate_count", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "refused_gap_count", sa.BigInteger(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "refused_old_count", sa.BigInteger(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("observed_gaps", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_id", "source_instance", name="uq_mon_sequence_instance"),
    )
    op.create_index("ix_mon_sequence_last_seen", "monitoring_sequence_state", ["last_seen_at"])

    # --- Quarantine forensics ---------------------------------------------
    op.create_table(
        "monitoring_raw_requests",
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=80), nullable=False),
        sa.Column("claimed_source_id", sa.String(length=80), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_encoding", sa.String(length=32), nullable=True),
        sa.Column("byte_length", sa.Integer(), nullable=False),
        sa.Column("body_sha256", sa.String(length=64), nullable=False),
        sa.Column("body", sa.LargeBinary(), nullable=False),
        sa.PrimaryKeyConstraint("request_id"),
    )
    op.create_index("ix_mon_raw_received_at", "monitoring_raw_requests", ["received_at"])

    op.create_table(
        "monitoring_quarantine",
        sa.Column("quarantine_id", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("message_id", sa.String(length=80), nullable=True),
        sa.Column("declared_message_id", sa.String(length=80), nullable=True),
        sa.Column("computed_message_id", sa.String(length=80), nullable=True),
        sa.Column("source_id", sa.String(length=80), nullable=False),
        sa.Column("claimed_source_id", sa.String(length=80), nullable=True),
        sa.Column("source_instance", sa.String(length=80), nullable=True),
        sa.Column("source_sequence", sa.String(length=24), nullable=True),
        sa.Column("schema_version", sa.String(length=32), nullable=True),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("request_sha256", sa.String(length=64), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("quarantine_id"),
    )
    op.create_index("ix_mon_quarantine_received_at", "monitoring_quarantine", ["received_at"])
    op.create_index("ix_mon_quarantine_reason", "monitoring_quarantine", ["source_id", "reason"])
    op.create_index("ix_mon_quarantine_request", "monitoring_quarantine", ["request_id"])

    # --- Derived projections ----------------------------------------------
    op.create_table(
        "monitoring_projections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "receiver_deployment_environment",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'UNKNOWN'"),
        ),
        sa.Column("source_id", sa.String(length=80), nullable=False),
        sa.Column("message_type", sa.String(length=48), nullable=False),
        sa.Column(
            "capture_ref", sa.String(length=160), nullable=False, server_default=sa.text("''")
        ),
        sa.Column("message_id", sa.String(length=80), nullable=False),
        sa.Column("source_instance", sa.String(length=80), nullable=False),
        sa.Column("source_sequence", sa.String(length=24), nullable=False),
        sa.Column("sequence_ordinal", sa.BigInteger(), nullable=False),
        sa.Column("source_environment", sa.String(length=32), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_as_of_json", sa.Text(), nullable=False),
        sa.Column("coverage_json", sa.Text(), nullable=False),
        sa.Column("freshness_json", sa.Text(), nullable=False),
        sa.Column("trust_json", sa.Text(), nullable=False),
        sa.Column("runtime_json", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "receiver_deployment_environment",
            "source_id",
            "message_type",
            "capture_ref",
            name="uq_mon_projection_key",
        ),
    )
    op.create_index(
        "ix_mon_projection_type",
        "monitoring_projections",
        ["receiver_deployment_environment", "message_type"],
    )

    # --- Receiver-side audit ----------------------------------------------
    op.create_table(
        "monitoring_audit",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.String(length=80), nullable=True),
        sa.Column("request_id", sa.String(length=64), nullable=True),
        sa.Column("remote_addr", sa.String(length=64), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mon_audit_at", "monitoring_audit", ["at"])
    op.create_index("ix_mon_audit_action", "monitoring_audit", ["action", "outcome"])


def downgrade() -> None:
    """Restore the a3c7e1d94b62 shape structurally.

    Rows are not restored. The two shapes hold different information and no
    faithful conversion exists — which is precisely why this migration is only
    safe while the tables are empty.
    """
    for table in (
        "monitoring_audit",
        "monitoring_projections",
        "monitoring_quarantine",
        "monitoring_raw_requests",
        "monitoring_sequence_state",
        "monitoring_evidence",
    ):
        op.drop_table(table)

    # Re-run the previous revision's creation by loading it from disk rather
    # than duplicating 200 lines of DDL that would drift out of step with it.
    import importlib.util
    import pathlib

    previous_path = pathlib.Path(__file__).with_name("a3c7e1d94b62_monitoring_v1_receiver.py")
    spec = importlib.util.spec_from_file_location("_monitoring_v1_previous", previous_path)
    assert spec is not None and spec.loader is not None
    previous = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(previous)
    previous.upgrade()
