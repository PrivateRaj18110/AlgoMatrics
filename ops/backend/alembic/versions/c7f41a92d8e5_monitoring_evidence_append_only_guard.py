"""monitoring_evidence — enforce append-only in the database, not only the ORM

``MonitoringEvidence`` carries ``before_update`` and ``before_delete`` mapper
events that raise ``EvidenceIsImmutable``. Staging validation established that
they are necessary but not sufficient: they guard the *object* path only.

Measured against real PostgreSQL, with the application's own role and session:

    session.flush() after an attribute change   REFUSED (EvidenceIsImmutable)
    session.delete(row)                         REFUSED (EvidenceIsImmutable)
    session.execute(update(MonitoringEvidence)) ALLOWED  - 1 row rewritten
    session.execute(delete(MonitoringEvidence)) ALLOWED  - 1 row destroyed
    raw SQL UPDATE / DELETE                     ALLOWED

SQLAlchemy Core bulk statements do not emit mapper events, so a bulk update, a
maintenance script, or anything that reaches SQL can silently rewrite evidence
that the rest of the system presents as an immutable forensic record. The
receiver's value rests on that record being unforgeable after the fact, so the
guarantee belongs where it cannot be stepped around.

This revision adds a row-level trigger that raises on UPDATE and DELETE. It is
additive: no table is dropped, no row is touched, and no column changes. Inserts
are unaffected.

``TRUNCATE`` is deliberately still permitted. Row-level triggers do not fire for
it, it requires table-owner privilege, and it cannot be aimed at a single row —
so it stays available for resetting a test database while remaining useless as a
way to quietly edit history.

Deletion is blocked outright rather than given an escape hatch. The retention
policy is explicitly undecided, and a future approved retention job should have
to drop this trigger in its own reviewed migration — making evidence deletion a
visible, deliberate act rather than an option left lying around.

PostgreSQL only. On SQLite — used for development and the offline suite — the
ORM guard remains the whole guarantee, which is documented in
``docs/monitoring/POSTGRESQL_VALIDATION.md`` rather than silently assumed.

Revision ID: c7f41a92d8e5
Revises: b5e83a17c246
Create Date: 2026-09-12
"""

from __future__ import annotations

from alembic import op

revision = "c7f41a92d8e5"
down_revision = "b5e83a17c246"
branch_labels = None
depends_on = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if not _is_postgresql():
        return

    op.execute(
        """
        CREATE OR REPLACE FUNCTION monitoring_evidence_is_append_only()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION
                'monitoring_evidence is append-only; % is not permitted on message_id=%',
                TG_OP,
                COALESCE(OLD.message_id, '<unknown>')
                USING HINT = 'Corrections arrive as new messages. Retention, if ever '
                             'approved, must drop this trigger in its own migration.',
                      ERRCODE = 'integrity_constraint_violation';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER monitoring_evidence_no_update
        BEFORE UPDATE ON monitoring_evidence
        FOR EACH ROW EXECUTE FUNCTION monitoring_evidence_is_append_only();
        """
    )
    op.execute(
        """
        CREATE TRIGGER monitoring_evidence_no_delete
        BEFORE DELETE ON monitoring_evidence
        FOR EACH ROW EXECUTE FUNCTION monitoring_evidence_is_append_only();
        """
    )


def downgrade() -> None:
    if not _is_postgresql():
        return
    op.execute("DROP TRIGGER IF EXISTS monitoring_evidence_no_delete ON monitoring_evidence;")
    op.execute("DROP TRIGGER IF EXISTS monitoring_evidence_no_update ON monitoring_evidence;")
    op.execute("DROP FUNCTION IF EXISTS monitoring_evidence_is_append_only();")
