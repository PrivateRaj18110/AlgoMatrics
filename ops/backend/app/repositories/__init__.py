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

from datetime import datetime, timezone
import json
from typing import Any

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

    def query(
        self,
        *,
        limit: int = 400,
        machine_id: str | None = None,
        session_id: str | None = None,
        event_type: str | None = None,
        strategy: str | None = None,
        symbol: str | None = None,
        severity: str | None = None,
        since=None,
        until=None,
    ) -> list[dict]:
        rows = self.list()
        if machine_id:
            rows = [r for r in rows if r.get("machine_id") == machine_id or r.get("machineId") == machine_id]
        if session_id:
            rows = [r for r in rows if r.get("session_id") == session_id or r.get("sessionId") == session_id]
        if event_type:
            rows = [r for r in rows if r.get("event_type") == event_type or r.get("eventType") == event_type]
        if strategy:
            rows = [r for r in rows if r.get("strategy") == strategy]
        if symbol:
            rows = [r for r in rows if r.get("symbol") == symbol]
        if severity:
            rows = [r for r in rows if r.get("severity") == severity]
        if since:
            rows = [r for r in rows if str(r.get("time", "")) >= since.isoformat()]
        if until:
            rows = [r for r in rows if str(r.get("time", "")) <= until.isoformat()]
        return rows[:limit]


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


class _NullSyncStateRepository:
    """Mock-mode sync state: accepted and discarded.

    Mock mode is a development convenience only — production refuses to start
    without a database (``Settings.assert_production_ready``), so nothing that
    matters is silently dropped here.
    """

    def get(self, machine_id: str, agent_id: str) -> dict | None:
        return None

    def record_batch(self, **_kwargs) -> dict:
        return {}

    def list(self) -> list[dict]:
        return []


class _InMemorySessionsRepository:
    """Mock-mode trading sessions, shaped like the durable SQL read model."""

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], dict[str, Any]] = {}

    def touch(
        self,
        *,
        session_id: str,
        machine_id: str,
        machine: str,
        event_time: datetime | None,
        is_trade: bool = False,
    ) -> None:
        key = (session_id, machine_id)
        ts = event_time.isoformat() if event_time else _now_iso()
        row = self._rows.get(key)
        if row is None:
            row = {
                "sessionId": session_id,
                "machineId": machine_id,
                "machine": machine,
                "status": "open",
                "startedAt": ts,
                "endedAt": None,
                "lastEventAt": ts,
                "eventCount": 0,
                "tradeCount": 0,
            }
            self._rows[key] = row
        row["eventCount"] += 1
        if is_trade:
            row["tradeCount"] += 1
        if not row.get("lastEventAt") or ts > row["lastEventAt"]:
            row["lastEventAt"] = ts

    def close(self, *, session_id: str, machine_id: str, ended_at: datetime | None) -> None:
        row = self._rows.get((session_id, machine_id))
        if row is None:
            return
        row["status"] = "closed"
        row["endedAt"] = ended_at.isoformat() if ended_at else _now_iso()

    def latest(self, machine_id: str) -> dict | None:
        rows = [row for row in self._rows.values() if row["machineId"] == machine_id]
        if not rows:
            return None
        return dict(max(rows, key=lambda row: row.get("lastEventAt") or ""))

    def get(self, session_id: str, *, machine_id: str | None = None) -> dict | None:
        rows = [
            row for row in self._rows.values()
            if row["sessionId"] == session_id
            and (machine_id is None or row["machineId"] == machine_id)
        ]
        if not rows:
            return None
        return dict(max(rows, key=lambda row: row.get("lastEventAt") or ""))

    def list(
        self,
        *,
        limit: int = 100,
        machine_id: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        rows = list(self._rows.values())
        if machine_id:
            rows = [row for row in rows if row["machineId"] == machine_id]
        if status:
            rows = [row for row in rows if row["status"] == status]
        return [
            dict(row)
            for row in sorted(rows, key=lambda row: row.get("lastEventAt") or "", reverse=True)[
                :limit
            ]
        ]


class _InMemoryDeadLetterRepository:
    """Mock-mode dead letters — kept in RAM so dev/tests can still assert them.

    Bounded so a misbehaving local agent cannot grow it without limit.
    """

    _CAP = 500

    def __init__(self) -> None:
        self._rows: list[dict] = []

    def insert(self, entry: dict) -> None:
        self._rows.insert(0, dict(entry))
        del self._rows[self._CAP:]

    def list(self) -> list[dict]:
        return list(self._rows)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class _InMemoryEodRepository:
    """Mock-mode EOD catalog, bounded to process memory."""

    def __init__(self) -> None:
        self._datasets: dict[str, dict[str, Any]] = {}

    def get(self, dataset_id: str, *, include_files: bool = True) -> dict | None:
        row = self._datasets.get(dataset_id)
        if row is None:
            return None
        copy = dict(row)
        copy["files"] = [dict(file) for file in row.get("files", [])] if include_files else []
        return copy

    def list(
        self,
        *,
        limit: int = 100,
        status: str | None = None,
        machine_id: str | None = None,
        trading_date: str | None = None,
    ) -> list[dict]:
        rows = [self.get(dataset_id, include_files=False) for dataset_id in self._datasets]
        clean = [row for row in rows if row is not None]
        if status:
            clean = [row for row in clean if row["status"] == status]
        if machine_id:
            clean = [row for row in clean if row["machineId"] == machine_id]
        if trading_date:
            clean = [row for row in clean if row["tradingDate"] == trading_date]
        return sorted(clean, key=lambda row: row["receivedAt"], reverse=True)[:limit]

    def create(self, dataset: dict[str, Any], files: list[dict[str, Any]]) -> dict:
        now = _now_iso()
        row = {
            **dataset,
            "status": dataset.get("status", "MANIFESTED"),
            "statusReason": dataset.get("statusReason"),
            "storageBackend": dataset.get("storageBackend", "local"),
            "totalFiles": len(files),
            "uploadedFiles": 0,
            "totalBytes": sum(int(file.get("sizeBytes", 0)) for file in files),
            "uploadedBytes": 0,
            "completedAt": None,
            "finalizedAt": None,
            "rawDeletedAt": None,
            "receivedAt": now,
            "updatedAt": now,
            "files": [
                {
                    **file,
                    "storageKey": file.get("storageKey"),
                    "bytesReceived": 0,
                    "status": "MANIFESTED",
                    "checksumStatus": None,
                    "failureReason": None,
                    "uploadedAt": None,
                    "validatedAt": None,
                }
                for file in files
            ],
        }
        self._datasets[row["datasetId"]] = row
        return self.get(row["datasetId"]) or row

    def update_dataset(self, dataset_id: str, changes: dict[str, Any]) -> dict | None:
        row = self._datasets.get(dataset_id)
        if row is None:
            return None
        row.update(changes)
        row["updatedAt"] = _now_iso()
        return self.get(dataset_id)

    def get_file(self, dataset_id: str, file_id: str) -> dict | None:
        row = self._datasets.get(dataset_id)
        if row is None:
            return None
        for file in row.get("files", []):
            if file["fileId"] == file_id:
                return dict(file)
        return None

    def update_file(self, dataset_id: str, file_id: str, changes: dict[str, Any]) -> dict | None:
        row = self._datasets.get(dataset_id)
        if row is None:
            return None
        for file in row.get("files", []):
            if file["fileId"] == file_id:
                file.update(changes)
                self._recalculate(row)
                row["updatedAt"] = _now_iso()
                return dict(file)
        return None

    def reconciliation(self) -> dict[str, Any]:
        datasets = list(self._datasets.values())
        files = [file for dataset in datasets for file in dataset.get("files", [])]
        by_status: dict[str, int] = {}
        for dataset in datasets:
            by_status[dataset["status"]] = by_status.get(dataset["status"], 0) + 1
        return {
            "total": len(datasets),
            "byStatus": by_status,
            "missingFiles": sum(1 for file in files if file["bytesReceived"] < file["sizeBytes"]),
            "failedFiles": sum(1 for file in files if file["status"] in {"FAILED", "CONFLICT"}),
            "checksumFailures": sum(1 for file in files if file.get("checksumStatus") == "FAILED"),
            "partialDatasets": sum(1 for dataset in datasets if dataset["status"] in {"PARTIAL", "UPLOADING"}),
        }

    @staticmethod
    def _recalculate(row: dict[str, Any]) -> None:
        files = row.get("files", [])
        row["uploadedFiles"] = sum(1 for file in files if file["status"] in {"READY", "COMPLETE"})
        row["uploadedBytes"] = sum(int(file.get("bytesReceived", 0)) for file in files)


class _InMemoryQuantReportRepository:
    """Mock-mode quant reports."""

    def __init__(self) -> None:
        self._rows: dict[str, dict[str, Any]] = {}

    def list(self, *, limit: int = 100, dataset_id: str | None = None) -> list[dict[str, Any]]:
        rows = list(self._rows.values())
        if dataset_id:
            rows = [row for row in rows if row["datasetId"] == dataset_id]
        sorted_rows = sorted(rows, key=lambda row: row["updatedAt"], reverse=True)[:limit]
        return [json.loads(json.dumps(row)) for row in sorted_rows]

    def get(self, report_id: str) -> dict[str, Any] | None:
        row = self._rows.get(report_id)
        return json.loads(json.dumps(row)) if row is not None else None

    def latest_for_dataset(self, dataset_id: str) -> dict[str, Any] | None:
        rows = self.list(limit=1, dataset_id=dataset_id)
        return rows[0] if rows else None

    def upsert(self, report: dict[str, Any]) -> dict[str, Any]:
        now = _now_iso()
        existing = self._rows.get(report["reportId"], {})
        row = {
            **report,
            "createdAt": existing.get("createdAt", now),
            "updatedAt": now,
        }
        self._rows[report["reportId"]] = row
        return self.get(report["reportId"]) or row


class _InMemorySystemHealthRepository:
    def __init__(self) -> None:
        self._rows: list[dict[str, Any]] = []

    def insert(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        event_id = snapshot.get("event_id") or snapshot.get("envelope_id")
        if event_id:
            for r in self._rows:
                if r.get("event_id") == event_id:
                    return r
        self._rows.append(snapshot)
        return snapshot

    def query(
        self,
        *,
        machine_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        rows = self._rows
        if machine_id:
            rows = [r for r in rows if r.get("machine_id") == machine_id]
        if since is not None:
            rows = [r for r in rows if str(r.get("timestamp_utc", "")) >= since.isoformat()]
        if until is not None:
            rows = [r for r in rows if str(r.get("timestamp_utc", "")) <= until.isoformat()]
        return sorted(rows, key=lambda r: str(r.get("timestamp_utc", "")))[:limit]


from app.repositories.sql import (
    SqlDeadLetterRepository,
    SqlEodRepository,
    SqlEventsRepository,
    SqlLogsRepository,
    SqlMachinesRepository,
    SqlMetricsRepository,
    SqlQuantReportRepository,
    SqlSessionsRepository,
    SqlSyncStateRepository,
    SqlSystemHealthRepository,
    SqlTradesRepository,
)


class _RepositoryProxy:
    def __init__(self, sql_factory, mock_factory):
        self._sql_factory = sql_factory
        self._mock_factory = mock_factory
        self._sql_instance = None
        self._mock_instance = None

    def _get_target(self):
        if database_enabled():
            if self._sql_instance is None:
                self._sql_instance = self._sql_factory()
            return self._sql_instance
        if self._mock_instance is None:
            self._mock_instance = self._mock_factory()
        return self._mock_instance

    def __getattr__(self, name: str):
        return getattr(self._get_target(), name)


machines_repo = _RepositoryProxy(SqlMachinesRepository, lambda: MachinesRepository(_data.MACHINES))
events_repo = _RepositoryProxy(SqlEventsRepository, lambda: EventsRepository(_data.EVENTS))
logs_repo = _RepositoryProxy(SqlLogsRepository, lambda: LogsRepository(_data.LOGS))
trades_repo = _RepositoryProxy(SqlTradesRepository, lambda: _MockTradesRepository(_data.TRADES))
metrics_repo = _RepositoryProxy(SqlMetricsRepository, _NullMetricsRepository)
sync_state_repo = _RepositoryProxy(SqlSyncStateRepository, _NullSyncStateRepository)
sessions_repo = _RepositoryProxy(SqlSessionsRepository, _InMemorySessionsRepository)
dead_letter_repo = _RepositoryProxy(SqlDeadLetterRepository, _InMemoryDeadLetterRepository)
eod_repo = _RepositoryProxy(SqlEodRepository, _InMemoryEodRepository)
quant_report_repo = _RepositoryProxy(SqlQuantReportRepository, _InMemoryQuantReportRepository)
system_health_repo = _RepositoryProxy(SqlSystemHealthRepository, _InMemorySystemHealthRepository)

# Idempotency + transaction primitives (no-ops in mock mode).
from app.repositories.sql import prune_dedup, reserve_envelope, unit_of_work  # noqa: E402


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
    "sync_state_repo", "sessions_repo", "dead_letter_repo", "eod_repo",
    "quant_report_repo", "system_health_repo",
    "dashboard_doc", "analytics_doc", "risk_doc", "execution_doc", "build_event",
    "reserve_envelope", "unit_of_work", "prune_dedup",
]
