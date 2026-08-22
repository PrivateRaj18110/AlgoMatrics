"""Read-only audit of ops blotter rows that look like misclassified telemetry.

Does not DELETE or UPDATE anything. Prints counts so a human can decide on a
cleanup plan. Genuine trades (non-zero entry/exit/pnl or a real strategy/symbol)
are left untouched.

Usage (from ops/backend, with DATABASE_URL pointing at the ops telemetry DB):

    python scripts/audit_misclassified_trades.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text  # noqa: E402

from app.database.session import database_enabled, get_engine  # noqa: E402


SUSPECT_SQL = """
SELECT
  COUNT(*) AS total_trades,
  SUM(CASE WHEN envelope_id IS NOT NULL THEN 1 ELSE 0 END) AS with_envelope_id,
  SUM(CASE WHEN envelope_id IS NULL THEN 1 ELSE 0 END) AS missing_envelope_id,
  SUM(CASE WHEN action IS NOT NULL THEN 1 ELSE 0 END) AS with_action,
  SUM(CASE WHEN COALESCE(strategy, '') IN ('', 'unknown') THEN 1 ELSE 0 END) AS missing_strategy,
  SUM(CASE WHEN COALESCE(entry, 0) = 0 THEN 1 ELSE 0 END) AS zero_entry,
  SUM(CASE WHEN exit IS NULL THEN 1 ELSE 0 END) AS null_exit,
  SUM(CASE WHEN COALESCE(pnl, 0) = 0 THEN 1 ELSE 0 END) AS zero_pnl,
  SUM(CASE WHEN COALESCE(duration_sec, 0) = 0 THEN 1 ELSE 0 END) AS zero_duration,
  SUM(CASE WHEN COALESCE(latency_ms, 0) = 0 THEN 1 ELSE 0 END) AS zero_latency,
  SUM(
    CASE WHEN COALESCE(strategy, '') IN ('', 'unknown')
              AND COALESCE(entry, 0) = 0
              AND exit IS NULL
              AND COALESCE(pnl, 0) = 0
              AND COALESCE(duration_sec, 0) = 0
              AND status = 'closed'
         THEN 1 ELSE 0 END
  ) AS likely_misclassified_telemetry
FROM trades
"""

SAMPLE_SQL = """
SELECT id, envelope_id, time, strategy, machine, symbol, direction, action,
       entry, exit, pnl, latency_ms, duration_sec, status
FROM trades
WHERE COALESCE(strategy, '') IN ('', 'unknown')
  AND COALESCE(entry, 0) = 0
  AND exit IS NULL
  AND COALESCE(pnl, 0) = 0
  AND COALESCE(duration_sec, 0) = 0
  AND status = 'closed'
ORDER BY time DESC
LIMIT 20
"""


def main() -> int:
    if not database_enabled():
        print("DATABASE_URL is not set; cannot audit production blotter rows.")
        return 2
    engine = get_engine()
    with engine.connect() as conn:
        counts = dict(conn.execute(text(SUSPECT_SQL)).mappings().one())
        samples = [dict(row) for row in conn.execute(text(SAMPLE_SQL)).mappings()]
    print(json.dumps({"counts": counts, "sample_suspect_rows": samples}, default=str, indent=2))
    print(
        "\nCleanup is NOT applied. If likely_misclassified_telemetry > 0, a safe "
        "follow-up is to archive those rows (envelope_id preserved) rather than "
        "DELETE, and never touch rows with real strategy/entry/exit/pnl."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
