"""Read-only access to the ops telemetry Postgres.

Unset ``OPS_DATABASE_URL`` → empty results (never fixtures).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from algo_platform.modules.operations.application.timestamps import to_utc_z


def _sync_url(url: str) -> str:
    return (
        url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
        .replace("postgresql+psycopg2://", "postgresql+psycopg://")
    )


class TelemetryStore:
    def __init__(self, database_url: str | None) -> None:
        self._url = (database_url or "").strip()
        self._engine: Engine | None = None
        if self._url:
            self._engine = create_engine(_sync_url(self._url), pool_pre_ping=True, future=True)

    @property
    def configured(self) -> bool:
        return self._engine is not None

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        if self._engine is None:
            raise RuntimeError("ops telemetry database is not configured")
        with self._engine.connect() as conn:
            yield conn

    def list_machines(self) -> list[dict[str, Any]]:
        if not self.configured:
            return []
        sql = text(
            """
            SELECT id, name, location, provider, status, cpu, ram, disk,
                   temperature_c, internet_ms, broker_ping_ms, python_status,
                   uptime_sec, last_heartbeat, strategy_count, agent_id,
                   agent_version, hostname, environment, last_event, last_trade,
                   last_error, last_successful_upload, queue_depth,
                   oldest_pending_age_sec, transport_state, current_session_id,
                   trading_process_state
            FROM machines
            ORDER BY created_at, id
            """
        )
        with self._connect() as conn:
            rows = conn.execute(sql).mappings().all()
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "hostname": row["hostname"] or row["name"],
                "agent_id": row["agent_id"],
                "status": row["status"],
                "cpu": row["cpu"],
                "ram": row["ram"],
                "disk": row["disk"],
                "temperature_c": row["temperature_c"],
                "internet_ms": row["internet_ms"],
                "broker_ping_ms": row["broker_ping_ms"],
                "uptime_sec": row["uptime_sec"],
                "last_heartbeat": to_utc_z(row["last_heartbeat"]),
                "strategy_count": row["strategy_count"],
                "last_successful_upload": to_utc_z(row["last_successful_upload"]),
                "queue_depth": row["queue_depth"],
                "oldest_pending_age_sec": row["oldest_pending_age_sec"],
                "transport_state": row["transport_state"],
                "environment": row["environment"] or None,
            }
            for row in rows
        ]

    def list_events(
        self,
        *,
        limit: int = 200,
        event_type: str | None = None,
        machine_id: str | None = None,
        strategy: str | None = None,
        symbol: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self.configured:
            return []
        clauses = ["1=1"]
        params: dict[str, Any] = {"limit": limit}
        if event_type:
            clauses.append("event_type = :event_type")
            params["event_type"] = event_type
        if machine_id:
            clauses.append("machine_id = :machine_id")
            params["machine_id"] = machine_id
        if strategy:
            clauses.append("strategy = :strategy")
            params["strategy"] = strategy
        if symbol:
            clauses.append("symbol = :symbol")
            params["symbol"] = symbol
        if since:
            clauses.append("time >= :since")
            params["since"] = since
        if until:
            clauses.append("time <= :until")
            params["until"] = until
        where = " AND ".join(clauses)
        sql = text(
            "SELECT id, time, created_at, category, severity, source, message, "  # noqa: S608
            "machine_id, event_type, strategy, symbol, session_id, sequence_id, "
            "payload_summary FROM events WHERE "
            + where
            + " ORDER BY time DESC, id DESC LIMIT :limit"
        )
        with self._connect() as conn:
            rows = conn.execute(sql, params).mappings().all()
        return [
            {
                "id": row["id"],
                "time": to_utc_z(row["time"]),
                "received_at": to_utc_z(row["created_at"]),
                "category": row["category"],
                "severity": row["severity"],
                "source": row["source"],
                "message": row["message"],
                "machine_id": row["machine_id"],
                "event_type": row["event_type"],
                "strategy": row["strategy"],
                "symbol": row["symbol"],
                "session_id": row["session_id"],
                "sequence_id": row["sequence_id"],
                "payload_summary": row["payload_summary"],
            }
            for row in rows
        ]

    def list_logs(self, *, limit: int = 200) -> list[dict[str, Any]]:
        if not self.configured:
            return []
        sql = text(
            """
            SELECT id, time, source, level, logger, message
            FROM logs
            ORDER BY time DESC, id DESC
            LIMIT :limit
            """
        )
        with self._connect() as conn:
            rows = conn.execute(sql, {"limit": limit}).mappings().all()
        return [
            {
                "id": row["id"],
                "time": to_utc_z(row["time"]),
                "source": row["source"],
                "level": row["level"],
                "logger": row["logger"],
                "message": row["message"],
            }
            for row in rows
        ]

    def list_trades(
        self,
        *,
        limit: int = 200,
        strategy: str | None = None,
        symbol: str | None = None,
        machine_id: str | None = None,
        include_suspect: bool = False,
    ) -> list[dict[str, Any]]:
        if not self.configured:
            return []
        clauses = ["1=1"]
        params: dict[str, Any] = {"limit": limit}
        if strategy:
            clauses.append("strategy = :strategy")
            params["strategy"] = strategy
        if symbol:
            clauses.append("symbol = :symbol")
            params["symbol"] = symbol
        if machine_id:
            clauses.append("machine_id = :machine_id")
            params["machine_id"] = machine_id
        if not include_suspect:
            clauses.append(
                """
                NOT (
                    lower(coalesce(strategy, '')) IN ('', 'unknown')
                    AND entry = 0
                    AND exit IS NULL
                    AND pnl = 0
                    AND duration_sec = 0
                    AND status = 'closed'
                )
                """
                )
        where = " AND ".join(clauses)
        sql = text(
            "SELECT id, time, strategy, machine, machine_id, broker, account, "  # noqa: S608
            "symbol, direction, action, entry, exit, quantity, pnl, latency_ms, "
            "duration_sec, status FROM trades WHERE "
            + where
            + " ORDER BY time DESC, id DESC LIMIT :limit"
        )
        with self._connect() as conn:
            rows = conn.execute(sql, params).mappings().all()
        return [
            {
                "id": row["id"],
                "time": to_utc_z(row["time"]),
                "strategy": row["strategy"] or None,
                "machine": row["machine"] or None,
                "machine_id": row["machine_id"],
                "broker": row["broker"] or None,
                "account": row["account"] or None,
                "symbol": row["symbol"] or None,
                "direction": row["direction"],
                "entry": row["entry"],
                "exit": row["exit"],
                "quantity": row["quantity"],
                "pnl": row["pnl"],
                "latency_ms": row["latency_ms"],
                "duration_sec": row["duration_sec"],
                "status": row["status"],
            }
            for row in rows
        ]
