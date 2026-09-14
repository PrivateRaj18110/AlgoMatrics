"""monitoring.v1 organisation customer partitioning

Adds non-null organisation_id to monitoring_evidence, monitoring_sequence_state,
and monitoring_projections. Adds nullable organisation_id to monitoring_quarantine,
monitoring_raw_requests, and monitoring_audit.

Updates unique constraints:
- monitoring_sequence_state: (organisation_id, source_id, source_instance)
- monitoring_projections: (receiver_deployment_environment, organisation_id, source_id, message_type, capture_ref)

Revision ID: d9e1f2a3b4c5
Revises: c7f41a92d8e5
Create Date: 2026-09-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d9e1f2a3b4c5"
down_revision = "c7f41a92d8e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- 1. monitoring_evidence ------------------------------------------
    with op.batch_alter_table("monitoring_evidence", schema=None) as batch_op:
        batch_op.add_column(sa.Column("organisation_id", sa.Uuid(), nullable=False))
        batch_op.create_index(
            "ix_mon_evidence_org_seq",
            ["organisation_id", "source_id", "source_instance", "sequence_ordinal"],
        )
        batch_op.create_index(
            "ix_mon_evidence_org_type",
            ["organisation_id", "message_type", "generated_at"],
        )

    # --- 2. monitoring_sequence_state ------------------------------------
    with op.batch_alter_table("monitoring_sequence_state", schema=None) as batch_op:
        batch_op.add_column(sa.Column("organisation_id", sa.Uuid(), nullable=False))
        batch_op.drop_constraint("uq_mon_sequence_instance", type_="unique")
        batch_op.create_unique_constraint(
            "uq_mon_sequence_instance",
            ["organisation_id", "source_id", "source_instance"],
        )
        batch_op.create_index("ix_mon_sequence_org", ["organisation_id"])

    # --- 3. monitoring_raw_requests --------------------------------------
    with op.batch_alter_table("monitoring_raw_requests", schema=None) as batch_op:
        batch_op.add_column(sa.Column("organisation_id", sa.Uuid(), nullable=True))
        batch_op.create_index("ix_mon_raw_org", ["organisation_id"])

    # --- 4. monitoring_quarantine ----------------------------------------
    with op.batch_alter_table("monitoring_quarantine", schema=None) as batch_op:
        batch_op.add_column(sa.Column("organisation_id", sa.Uuid(), nullable=True))
        batch_op.create_index("ix_mon_quarantine_org", ["organisation_id"])

    # --- 5. monitoring_projections ---------------------------------------
    with op.batch_alter_table("monitoring_projections", schema=None) as batch_op:
        batch_op.add_column(sa.Column("organisation_id", sa.Uuid(), nullable=False))
        batch_op.drop_constraint("uq_mon_projection_key", type_="unique")
        batch_op.create_unique_constraint(
            "uq_mon_projection_key",
            [
                "receiver_deployment_environment",
                "organisation_id",
                "source_id",
                "message_type",
                "capture_ref",
            ],
        )
        batch_op.drop_index("ix_mon_projection_type")
        batch_op.create_index(
            "ix_mon_projection_type",
            ["receiver_deployment_environment", "organisation_id", "message_type"],
        )

    # --- 6. monitoring_audit ---------------------------------------------
    with op.batch_alter_table("monitoring_audit", schema=None) as batch_op:
        batch_op.add_column(sa.Column("organisation_id", sa.Uuid(), nullable=True))
        batch_op.create_index("ix_mon_audit_org", ["organisation_id"])


def downgrade() -> None:
    # --- 6. monitoring_audit ---------------------------------------------
    with op.batch_alter_table("monitoring_audit", schema=None) as batch_op:
        batch_op.drop_index("ix_mon_audit_org")
        batch_op.drop_column("organisation_id")

    # --- 5. monitoring_projections ---------------------------------------
    with op.batch_alter_table("monitoring_projections", schema=None) as batch_op:
        batch_op.drop_index("ix_mon_projection_type")
        batch_op.create_index(
            "ix_mon_projection_type",
            ["receiver_deployment_environment", "message_type"],
        )
        batch_op.drop_constraint("uq_mon_projection_key", type_="unique")
        batch_op.create_unique_constraint(
            "uq_mon_projection_key",
            [
                "receiver_deployment_environment",
                "source_id",
                "message_type",
                "capture_ref",
            ],
        )
        batch_op.drop_column("organisation_id")

    # --- 4. monitoring_quarantine ----------------------------------------
    with op.batch_alter_table("monitoring_quarantine", schema=None) as batch_op:
        batch_op.drop_index("ix_mon_quarantine_org")
        batch_op.drop_column("organisation_id")

    # --- 3. monitoring_raw_requests --------------------------------------
    with op.batch_alter_table("monitoring_raw_requests", schema=None) as batch_op:
        batch_op.drop_index("ix_mon_raw_org")
        batch_op.drop_column("organisation_id")

    # --- 2. monitoring_sequence_state ------------------------------------
    with op.batch_alter_table("monitoring_sequence_state", schema=None) as batch_op:
        batch_op.drop_index("ix_mon_sequence_org")
        batch_op.drop_constraint("uq_mon_sequence_instance", type_="unique")
        batch_op.create_unique_constraint(
            "uq_mon_sequence_instance",
            ["source_id", "source_instance"],
        )
        batch_op.drop_column("organisation_id")

    # --- 1. monitoring_evidence ------------------------------------------
    with op.batch_alter_table("monitoring_evidence", schema=None) as batch_op:
        batch_op.drop_index("ix_mon_evidence_org_type")
        batch_op.drop_index("ix_mon_evidence_org_seq")
        batch_op.drop_column("organisation_id")
