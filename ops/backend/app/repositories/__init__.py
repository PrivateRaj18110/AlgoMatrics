"""Repository singletons.

The five live telemetry entities (machines, events, logs, trades, metrics) are
backed by **PostgreSQL** when ``DATABASE_URL`` is configured, and by the in-memory
mock fixtures otherwise. Either way the method surface and returned dict shapes
are identical, so the service / router / websocket layers above never change.

Strategies, brokers, accounts, alerts and the dashboard/analytics/risk/execution
document aggregates remain mock in this milestone (out of scope) and are built
the same way in both modes.
"""

from __future__ import annotations

from app.database.session import database_enabled
from app.repositories import mock_data as _data
from app.repositories.base import InMemoryRepository


# --------------------------------------------------------------------------- #
# In-memory implementations (mock mode + the always-mock entities)
# --------------------------------------------------------------------------- #
class MachinesRepository(InMemoryRepository[dict]):
    """Machines support live upsert so the Raj Local Agent can register hosts and
    stream telemetry into the same feed the dashboard already reads."""

    def upsert(self, machine: dict) -> dict:
        mid = machine.get(self._id_key)
        for i, row in enumerate(self._rows):
            if isinstance(row, dict) and row.get(self._id_key) == mid:
                row.update(machine)
                return row
        self._rows.append(machine)
        return machine

    def update(self, machine_id: str, changes: dict) -> dict | None:
        row = self.get(machine_id)
        if row is not None:
            row.update(changes)
        return row


class EventsRepository(InMemoryRepository[dict]):
    """Events also support live append (used by the SDK ingest + websocket)."""

    def prepend(self, event: dict) -> None:
        self._rows.insert(0, event)
        del self._rows[400:]


class LogsRepository(InMemoryRepository[dict]):
    """Logs support filtering by stream."""

    def by_source(self, source: str | None) -> list[dict]:
        rows = self.list()
        return [r for r in rows if r["source"] == source] if source else rows

    def prepend(self, entry: dict) -> None:
        self._rows.insert(0, entry)
        del self._rows[1000:]


class _MockTradesRepository(InMemoryRepository[dict]):
    """Read-only blotter in mock mode; ``insert`` is a no-op so the agent's trade
    persistence path is a clean no-op when no database is configured."""

    def insert(self, trade: dict) -> None:  # noqa: D401 - parity with SQL repo
        return None


class _NullMetricsRepository:
    """No metrics store in mock mode (there is no metrics endpoint)."""

    def insert(self, metric: dict) -> None:
        return None

    def list(self) -> list[dict]:
        return []


# --------------------------------------------------------------------------- #
# Scoped repositories: PostgreSQL when DATABASE_URL is set, else in-memory mock.
# --------------------------------------------------------------------------- #
if database_enabled():
    from app.repositories.sql import (
        SqlEventsRepository,
        SqlLogsRepository,
        SqlMachinesRepository,
        SqlMetricsRepository,
        SqlTradesRepository,
    )

    machines_repo = SqlMachinesRepository()
    events_repo = SqlEventsRepository()
    logs_repo = SqlLogsRepository()
    trades_repo = SqlTradesRepository()
    metrics_repo = SqlMetricsRepository()
else:
    machines_repo = MachinesRepository(_data.MACHINES)
    events_repo = EventsRepository(_data.EVENTS)
    logs_repo = LogsRepository(_data.LOGS)
    trades_repo = _MockTradesRepository(_data.TRADES)
    metrics_repo = _NullMetricsRepository()

# Idempotency + transaction primitives (no-ops in mock mode).
from app.repositories.sql import reserve_envelope, unit_of_work  # noqa: E402


# --------------------------------------------------------------------------- #
# Always-mock entities (out of scope for the DB migration).
# --------------------------------------------------------------------------- #
strategies_repo = InMemoryRepository(_data.STRATEGIES)
brokers_repo = InMemoryRepository(_data.BROKERS)
accounts_repo = InMemoryRepository(_data.ACCOUNT_LIST)
alerts_repo = InMemoryRepository(_data.ALERTS)

dashboard_doc = _data.DASHBOARD
analytics_doc = _data.ANALYTICS
risk_doc = _data.RISK
execution_doc = _data.EXECUTION

build_event = _data.build_event

__all__ = [
    "machines_repo", "strategies_repo", "trades_repo", "brokers_repo",
    "accounts_repo", "alerts_repo", "events_repo", "logs_repo", "metrics_repo",
    "dashboard_doc", "analytics_doc", "risk_doc", "execution_doc", "build_event",
    "reserve_envelope", "unit_of_work",
]
