"""Prune expired idempotency rows from ``ingest_dedup``.

Run on a schedule (see ``deploy/k8s/47-ops-prune.yaml``). Without it the table
grows by one row per ingested envelope forever.

    python -m scripts.prune_dedup [--days N] [--dry-run]

**Retention is a correctness setting, not just housekeeping.** An envelope
replayed after its dedup row has been pruned is processed a *second* time, so
the window must exceed the agent's longest realistic offline period. The agent's
durable queue holds 100,000 envelopes — roughly 14 trading sessions of telemetry
— so raise ``INGEST_DEDUP_RETENTION_DAYS`` before tolerating an outage longer
than the configured window.
"""

from __future__ import annotations

import argparse
import logging
import sys

from app.core.config import get_settings
from app.database.session import database_enabled

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ops.prune_dedup")


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Prune expired ingest_dedup rows.")
    parser.add_argument(
        "--days", type=int, default=settings.ingest_dedup_retention_days,
        help="Retention window in days (default: INGEST_DEDUP_RETENTION_DAYS).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report how many rows would be removed without deleting them.",
    )
    args = parser.parse_args(argv)

    if not database_enabled():
        log.error("DATABASE_URL is not configured — nothing to prune.")
        return 1
    if args.days <= 0:
        log.error("Retention must be positive; got %s.", args.days)
        return 1

    # Imported here so the module can be introspected without a database.
    from datetime import timedelta

    from sqlalchemy import func, select

    from app.database.session import get_sessionmaker
    from app.models import IngestDedup, utcnow
    from app.repositories import prune_dedup

    cutoff = utcnow() - timedelta(days=args.days)

    if args.dry_run:
        session = get_sessionmaker()()
        try:
            expired = session.execute(
                select(func.count()).select_from(IngestDedup)
                .where(IngestDedup.processed_at < cutoff)
            ).scalar_one()
        finally:
            session.close()
        log.info("dry run: %d row(s) older than %s would be removed", expired, cutoff)
        return 0

    removed = prune_dedup(args.days)
    log.info("pruned %d ingest_dedup row(s) older than %s", removed, cutoff)
    return 0


if __name__ == "__main__":
    sys.exit(main())
