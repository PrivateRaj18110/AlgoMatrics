"""Immutable, tamper-evident audit log.

Adds correlation/session identifiers and a SHA-256 hash chain to ``audit_log``,
backfills the chain over existing rows, and installs a trigger that makes the
table strictly append-only (UPDATE/DELETE raise).

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from algo_platform.modules.audit.application.hashing import (
    GENESIS_HASH,
    AuditFacts,
    compute_entry_hash,
)

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_IMMUTABLE_FN = """
CREATE OR REPLACE FUNCTION audit_log_prevent_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only; % is not permitted', TG_OP;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    # IF NOT EXISTS keeps fresh metadata-driven installs compatible with older
    # databases created before this revision.
    for name, ddl in (
        ("correlation_id", "VARCHAR(64)"),
        ("session_id", "VARCHAR(64)"),
        ("sequence", "BIGINT"),
        ("prev_hash", "VARCHAR(64)"),
        ("entry_hash", "VARCHAR(64)"),
    ):
        op.execute(f"ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS {name} {ddl}")

    _backfill_chain()

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_audit_log_correlation "
        "ON audit_log (correlation_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_audit_log_sequence "
        "ON audit_log (sequence)"
    )

    # Enforce append-only at the database, independent of application code.
    op.execute(_IMMUTABLE_FN)
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_mutation ON audit_log")
    op.execute(
        "CREATE TRIGGER audit_log_no_mutation "
        "BEFORE UPDATE OR DELETE ON audit_log "
        "FOR EACH ROW EXECUTE FUNCTION audit_log_prevent_mutation()"
    )


def _backfill_chain() -> None:
    bind = op.get_bind()
    # Continue from any rows already chained (e.g. a partially applied run).
    tip = bind.execute(
        sa.text(
            "SELECT sequence, entry_hash FROM audit_log "
            "WHERE sequence IS NOT NULL ORDER BY sequence DESC LIMIT 1"
        )
    ).first()
    next_seq = (tip.sequence + 1) if tip else 1
    prev_hash = tip.entry_hash if tip and tip.entry_hash else GENESIS_HASH

    rows = bind.execute(
        sa.text(
            "SELECT id, occurred_at, action, resource_type, resource_id, actor_type, "
            "actor_user_id, organization_id, request_id, correlation_id, session_id, "
            "ip_hash, before_state, after_state FROM audit_log "
            "WHERE sequence IS NULL ORDER BY occurred_at ASC, id ASC"
        )
    ).all()

    for row in rows:
        facts = AuditFacts(
            sequence=next_seq,
            occurred_at=row.occurred_at,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id or "",
            actor_type=row.actor_type,
            actor_user_id=row.actor_user_id,
            organization_id=row.organization_id,
            request_id=row.request_id,
            correlation_id=row.correlation_id,
            session_id=row.session_id,
            ip_hash=row.ip_hash,
            before_state=row.before_state,
            after_state=row.after_state,
        )
        entry_hash = compute_entry_hash(prev_hash, facts)
        bind.execute(
            sa.text(
                "UPDATE audit_log SET sequence = :seq, prev_hash = :prev, "
                "entry_hash = :hash WHERE id = :id"
            ),
            {"seq": next_seq, "prev": prev_hash, "hash": entry_hash, "id": row.id},
        )
        prev_hash = entry_hash
        next_seq += 1


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_mutation ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_prevent_mutation()")
    op.execute("DROP INDEX IF EXISTS ix_audit_log_sequence")
    op.execute("DROP INDEX IF EXISTS ix_audit_log_correlation")
    for name in ("entry_hash", "prev_hash", "sequence", "session_id", "correlation_id"):
        op.execute(f"ALTER TABLE audit_log DROP COLUMN IF EXISTS {name}")
