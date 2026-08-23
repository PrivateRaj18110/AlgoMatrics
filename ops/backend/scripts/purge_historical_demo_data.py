"""Audit and purge historical demo/seed data from Ops PostgreSQL.

Removes seeded mock identities (London VPS, Personal Computer, demo strategies,
trades without envelope_id) while preserving genuine telemetry and classified trades.

Usage:
    # Dry-run inspection
    python scripts/purge_historical_demo_data.py --dry-run

    # Execute purge
    python scripts/purge_historical_demo_data.py --execute
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text  # noqa: E402

from app.core.mock_policy import (  # noqa: E402
    DEMO_ACCOUNT_NAMES,
    DEMO_BROKER_NAMES,
    DEMO_MACHINE_IDS,
    DEMO_MACHINE_NAMES,
    DEMO_STRATEGY_NAMES,
)
from app.database.session import database_enabled, get_engine  # noqa: E402

DEMO_MACHINES_SELECT_SQL = """
SELECT id, name, provider, status, live, created_at
FROM machines
WHERE id IN ('mch-london', 'mch-gcloud', 'mch-pc')
   OR name IN ('London VPS', 'Personal Computer')
   OR live IS FALSE
   OR live = 0
"""

DEMO_TRADES_SELECT_SQL = """
SELECT id, envelope_id, strategy, machine, broker, account, pnl, time
FROM trades
WHERE envelope_id IS NULL
   OR machine_id IN ('mch-london', 'mch-gcloud', 'mch-pc')
   OR machine IN ('London VPS', 'Personal Computer')
   OR lower(strategy) IN (
       'mean reversion fx', 'momentum breakout', 'gold scalper',
       'stat arb pairs', 'crypto trend', 'index overnight',
       'news fade', 'grid hedge', 'vol harvest'
   )
   OR lower(broker) IN ('ic markets', 'pepperstone', 'interactive brokers', 'binance')
   OR lower(account) IN ('live-001', 'live-002', 'live-003', 'prop-114', 'demo-001')
"""

DEMO_EVENTS_SELECT_SQL = """
SELECT id, envelope_id, category, severity, source, strategy, time
FROM events
WHERE machine_id IN ('mch-london', 'mch-gcloud', 'mch-pc')
   OR source IN ('London VPS', 'Personal Computer')
   OR lower(strategy) IN (
       'mean reversion fx', 'momentum breakout', 'gold scalper',
       'stat arb pairs', 'crypto trend', 'index overnight',
       'news fade', 'grid hedge', 'vol harvest'
   )
"""

DEMO_LOGS_SELECT_SQL = """
SELECT id, time, source, level, logger, message
FROM logs
WHERE source IN ('host.london', 'host.pc', 'London VPS', 'Personal Computer')
   OR logger IN ('MR-FX', 'MOM', 'GRID', 'XAU-SC', 'ARB', 'CT', 'IDX-ON', 'NF', 'VOL')
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Purge historical demo data from Ops PostgreSQL")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute the deletion of demo records (defaults to dry-run)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Dry run without modifying database",
    )
    args = parser.parse_args()
    execute = bool(args.execute)

    if not database_enabled():
        print("DATABASE_URL is not set; cannot connect to Ops PostgreSQL.")
        return 2

    engine = get_engine()
    with engine.connect() as conn:
        demo_machines = [dict(r) for r in conn.execute(text(DEMO_MACHINES_SELECT_SQL)).mappings()]
        demo_trades = [dict(r) for r in conn.execute(text(DEMO_TRADES_SELECT_SQL)).mappings()]
        demo_events = [dict(r) for r in conn.execute(text(DEMO_EVENTS_SELECT_SQL)).mappings()]
        demo_logs = [dict(r) for r in conn.execute(text(DEMO_LOGS_SELECT_SQL)).mappings()]

    summary = {
        "mode": "EXECUTE" if execute else "DRY_RUN",
        "counts": {
            "demo_machines": len(demo_machines),
            "demo_trades": len(demo_trades),
            "demo_events": len(demo_events),
            "demo_logs": len(demo_logs),
        },
        "sample_machines": demo_machines[:5],
        "sample_trades": demo_trades[:5],
    }
    print(json.dumps(summary, default=str, indent=2))

    if not execute:
        print("\n[DRY RUN] No records were deleted. Run with --execute to remove these demo rows.")
        return 0

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                DELETE FROM machines
                WHERE id IN ('mch-london', 'mch-gcloud', 'mch-pc')
                   OR name IN ('London VPS', 'Personal Computer')
                   OR live IS FALSE
                   OR live = 0
                """
            )
        )
        conn.execute(
            text(
                """
                DELETE FROM trades
                WHERE envelope_id IS NULL
                   OR machine_id IN ('mch-london', 'mch-gcloud', 'mch-pc')
                   OR machine IN ('London VPS', 'Personal Computer')
                   OR lower(strategy) IN (
                       'mean reversion fx', 'momentum breakout', 'gold scalper',
                       'stat arb pairs', 'crypto trend', 'index overnight',
                       'news fade', 'grid hedge', 'vol harvest'
                   )
                   OR lower(broker) IN ('ic markets', 'pepperstone', 'interactive brokers', 'binance')
                   OR lower(account) IN ('live-001', 'live-002', 'live-003', 'prop-114', 'demo-001')
                """
            )
        )
        conn.execute(
            text(
                """
                DELETE FROM events
                WHERE machine_id IN ('mch-london', 'mch-gcloud', 'mch-pc')
                   OR source IN ('London VPS', 'Personal Computer')
                   OR lower(strategy) IN (
                       'mean reversion fx', 'momentum breakout', 'gold scalper',
                       'stat arb pairs', 'crypto trend', 'index overnight',
                       'news fade', 'grid hedge', 'vol harvest'
                   )
                """
            )
        )
        conn.execute(
            text(
                """
                DELETE FROM logs
                WHERE source IN ('host.london', 'host.pc', 'London VPS', 'Personal Computer')
                   OR logger IN ('MR-FX', 'MOM', 'GRID', 'XAU-SC', 'ARB', 'CT', 'IDX-ON', 'NF', 'VOL')
                """
            )
        )

    print("\n[SUCCESS] Historical demo records successfully deleted from Ops PostgreSQL.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
