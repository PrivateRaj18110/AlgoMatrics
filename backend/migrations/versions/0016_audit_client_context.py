"""Audit log client context: IP address, browser and resolved location.

Additive only. Existing rows keep NULLs and therefore keep exactly the hash
they were written with (the client fact is only hashed when present).

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-19
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ADD COLUMN IF NOT EXISTS: the metadata-driven baseline (0001) already creates
# these columns on a fresh install, so this must be a no-op there.
_COLUMNS = {
    "ip_address": "VARCHAR(45)",
    "user_agent": "VARCHAR(400)",
    "geo": "JSONB",
}


def upgrade() -> None:
    for name, ddl in _COLUMNS.items():
        op.execute(f"ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS {name} {ddl}")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_log_ip_address ON audit_log (ip_address)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_audit_log_ip_address")
    for name in _COLUMNS:
        op.execute(f"ALTER TABLE audit_log DROP COLUMN IF EXISTS {name}")
