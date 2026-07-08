#!/usr/bin/env bash
# Container entrypoint. The first argument selects the process; "migrate" and
# "seed" are one-shot helpers, the rest are long-running platform processes.
set -euo pipefail

wait_for_db() {
  echo "[entrypoint] waiting for database…"
  python - <<'PY'
import asyncio
import os
import sys

import asyncpg

url = os.environ["DATABASE_URL"].replace("+asyncpg", "")


async def main() -> None:
    for attempt in range(60):
        try:
            conn = await asyncpg.connect(url)
            await conn.close()
            print("[entrypoint] database is ready")
            return
        except Exception as error:  # noqa: BLE001
            print(f"[entrypoint] db not ready ({attempt}): {type(error).__name__}")
            await asyncio.sleep(2)
    print("[entrypoint] database did not become ready", file=sys.stderr)
    sys.exit(1)


asyncio.run(main())
PY
}

command="${1:-api}"

case "${command}" in
  migrate)
    wait_for_db
    echo "[entrypoint] running migrations…"
    alembic -c backend/alembic.ini upgrade head
    echo "[entrypoint] seeding reference data…"
    python scripts/seed.py
    ;;
  seed)
    wait_for_db
    python scripts/seed.py
    ;;
  api)
    exec python -m algo_platform.processes.api
    ;;
  worker)
    exec python -m algo_platform.processes.worker
    ;;
  engine)
    exec python -m algo_platform.processes.trading_engine
    ;;
  market-data)
    exec python -m algo_platform.processes.market_data
    ;;
  scheduler)
    exec python -m algo_platform.processes.scheduler
    ;;
  *)
    exec "$@"
    ;;
esac
