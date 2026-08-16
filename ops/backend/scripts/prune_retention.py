"""Run disabled-by-default ops retention policies.

Use ``--dry-run`` before enabling destructive policies. Each policy is governed
by its own environment variable; defaults are zero (disabled), except the
separate ingest-dedup correctness job handled by ``scripts.prune_dedup``.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from app.database.session import database_enabled
from app.services.retention_service import run_retention

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("ops.retention")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run ops telemetry/EOD/quant retention.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report matching rows/objects without deleting anything.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the retention summary as JSON.",
    )
    args = parser.parse_args(argv)

    if not database_enabled():
        log.error("DATABASE_URL is not configured — retention requires the ops database.")
        return 1

    summary = run_retention(dry_run=args.dry_run)
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        mode = "dry run" if args.dry_run else "prune"
        log.info(
            "%s complete: matched=%d deleted=%d",
            mode,
            summary["matched"],
            summary["deleted"],
        )
        for policy in summary["policies"]:
            log.info(
                "%s days=%s matched=%s deleted=%s note=%s",
                policy["policy"],
                policy["retentionDays"],
                policy["matched"],
                policy["deleted"],
                policy.get("note") or "",
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
