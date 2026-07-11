"""One-time demo seeding for the database-backed deployment.

Loads the mock ``MACHINES`` + ``TRADES`` fixtures so the dashboard's Machines
and blotter pages aren't empty in a fresh prod-like database. Events, logs and
metrics are intentionally *not* seeded — they fill in live from real agents.

Idempotent: only seeds a table that is currently empty, so it is safe to call on
every startup. A no-op when ``DATABASE_URL`` is unset (mock mode).
"""

from __future__ import annotations

from app.database.session import database_enabled
from app.repositories import machines_repo, trades_repo
from app.repositories import mock_data as _data


def seed_if_empty() -> dict[str, int]:
    """Seed demo machines/trades when their tables are empty. Returns counts."""
    if not database_enabled():
        return {"machines": 0, "trades": 0}

    seeded = {"machines": 0, "trades": 0}

    if not machines_repo.list():
        for machine in _data.MACHINES:
            # Seeded hosts are demo placeholders (live=False) — a real agent
            # registering the same name creates its own live `mch-agent-…` card.
            machines_repo.upsert(dict(machine))
            seeded["machines"] += 1

    if not trades_repo.list():
        for trade in _data.TRADES:
            trades_repo.insert(dict(trade))
            seeded["trades"] += 1

    return seeded
