"""Read-only access to the ops telemetry Postgres.

Unset ``OPS_DATABASE_URL``:
- local/test → empty lists (never fixtures)
- production → ``UnavailableError`` (fail closed)

No migration: this layer reads the existing ops-api tables.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from algo_platform.modules.operations.application.machine_status import derive_machine_status
from algo_platform.modules.operations.application.timestamps import to_utc_z
from algo_platform.shared.domain.errors import UnavailableError

_SUSPECT_SQL = """
NOT (
    lower(coalesce(strategy, '')) IN ('', 'unknown')
    AND entry = 0
    AND exit IS NULL
    AND pnl = 0
    AND duration_sec = 0
    AND status = 'closed'
)
"""

_DEMO_TRADE_SQL = """
NOT (
    coalesce(machine_id, '') IN ('mch-london', 'mch-gcloud', 'mch-pc')
    OR coalesce(id, '') LIKE 'trd-demo-%'
    OR coalesce(id, '') LIKE 'demo-%'
    OR coalesce(account, '') IN ('DEMO_MOCK_ACCOUNT', 'MOCK_ACCOUNT')
)
"""



def _sync_url(url: str) -> str:
    return (
        url.replace("postgresql+asyncpg://", "postgresql+psycopg://")
        .replace("postgresql+psycopg2://", "postgresql+psycopg://")
    )


def _blank_to_none(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


class TelemetryStore:
    def __init__(self, database_url: str | None) -> None:
        self._url = (database_url or "").strip()
        self._engine: Engine | None = None
        if self._url:
            connect_args = {"check_same_thread": False} if self._url.startswith("sqlite") else {}
            self._engine = create_engine(
                _sync_url(self._url),
                pool_pre_ping=True,
                future=True,
                connect_args=connect_args,
            )

    @property
    def configured(self) -> bool:
        return self._engine is not None

    def close(self) -> None:
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        if self._engine is None:
            raise UnavailableError("OPS_DATABASE_URL is not configured")
        try:
            with self._engine.connect() as conn:
                yield conn
        except SQLAlchemyError as exc:
            raise UnavailableError("ops telemetry database is unavailable") from exc
        except (ImportError, ModuleNotFoundError) as exc:
            raise UnavailableError("ops telemetry database is unavailable") from exc
        except BaseExceptionGroup as exc:
            if any(
                isinstance(inner, (SQLAlchemyError, ImportError, ModuleNotFoundError))
                for inner in exc.exceptions
            ):
                raise UnavailableError("ops telemetry database is unavailable") from exc
            raise

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
                   trading_process_state, live
            FROM machines
            WHERE live IS TRUE
              AND id NOT IN ('mch-london', 'mch-gcloud', 'mch-pc')
              AND name NOT IN ('London VPS', 'Personal Computer')
            ORDER BY created_at, id
            """
        )
        with self._connect() as conn:
            rows = conn.execute(sql).mappings().all()
        out = []
        for row in rows:
            heartbeat = row["last_heartbeat"]
            live = bool(row["live"]) if row["live"] is not None else True
            out.append(
                {
                    "id": row["id"],
                    "name": row["name"],
                    "hostname": _blank_to_none(row["hostname"]) or row["name"],
                    "agent_id": _blank_to_none(row["agent_id"]),
                    "status": derive_machine_status(row["status"], heartbeat, live=live),
                    "cpu": row["cpu"],
                    "ram": row["ram"],
                    "disk": row["disk"],
                    "temperature_c": row["temperature_c"],
                    "internet_ms": row["internet_ms"],
                    "broker_ping_ms": row["broker_ping_ms"],
                    "uptime_sec": row["uptime_sec"],
                    "last_heartbeat": to_utc_z(heartbeat),
                    "strategy_count": row["strategy_count"],
                    "last_successful_upload": to_utc_z(row["last_successful_upload"]),
                    "queue_depth": row["queue_depth"],
                    "oldest_pending_age_sec": row["oldest_pending_age_sec"],
                    "transport_state": _blank_to_none(row["transport_state"]),
                    "environment": _blank_to_none(row["environment"]),
                }
            )
        return out

    def list_events(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
        event_type: str | None = None,
        machine_id: str | None = None,
        strategy: str | None = None,
        symbol: str | None = None,
        since: str | None = None,
        until: str | None = None,
        severity: str | None = None,
        alert_only: bool = False,
    ) -> list[dict[str, Any]]:
        if not self.configured:
            return []
        clauses = [
            "1=1",
            "coalesce(machine_id, '') NOT IN ('mch-london', 'mch-gcloud', 'mch-pc')",
            "coalesce(source, '') NOT IN ('London VPS', 'Personal Computer')",
        ]
        params: dict[str, Any] = {"limit": limit, "offset": offset}
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
        if severity:
            clauses.append("severity = :severity")
            params["severity"] = severity
        if alert_only:
            clauses.append("(event_type IN ('alert', 'error') OR severity = 'critical')")
        where = " AND ".join(clauses)
        sql = text(
            "SELECT id, time, created_at, category, severity, source, message, "  # noqa: S608
            "machine_id, event_type, strategy, symbol, session_id, sequence_id, "
            "payload_summary FROM events WHERE "
            + where
            + " ORDER BY time DESC, id DESC LIMIT :limit OFFSET :offset"
        )
        with self._connect() as conn:
            rows = conn.execute(sql, params).mappings().all()
        return [
            {
                "id": row["id"],
                "time": to_utc_z(row["time"]),
                "received_at": to_utc_z(row["created_at"]),
                "ingest_ts": to_utc_z(row["created_at"]),
                "event_ts": to_utc_z(row["time"]),
                "category": row["category"],
                "severity": row["severity"],
                "source": row["source"],
                "message": row["message"],
                "machine_id": row["machine_id"],
                "event_type": row["event_type"],
                "strategy": _blank_to_none(row["strategy"]),
                "symbol": _blank_to_none(row["symbol"]),
                "session_id": row["session_id"],
                "sequence_id": row["sequence_id"],
                "payload_summary": row["payload_summary"],
            }
            for row in rows
        ]

    def list_logs(self, *, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
        if not self.configured:
            return []
        sql = text(
            """
            SELECT id, time, source, level, logger, message
            FROM logs
            WHERE coalesce(source, '') NOT IN (
                'host.london', 'host.pc', 'London VPS', 'Personal Computer'
            )
              AND coalesce(logger, '') NOT IN (
                'MR-FX', 'MOM', 'GRID', 'XAU-SC', 'ARB', 'CT', 'IDX-ON', 'NF', 'VOL'
            )
            ORDER BY time DESC, id DESC
            LIMIT :limit OFFSET :offset
            """
        )
        with self._connect() as conn:
            rows = conn.execute(sql, {"limit": limit, "offset": offset}).mappings().all()
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

    def _trade_where(
        self,
        *,
        strategy: str | None,
        symbol: str | None,
        machine_id: str | None,
        direction: str | None,
        status: str | None,
        since: str | None,
        until: str | None,
        include_suspect: bool,
        params: dict[str, Any],
    ) -> str:
        clauses = ["1=1", _DEMO_TRADE_SQL]
        if strategy:
            clauses.append("strategy = :strategy")
            params["strategy"] = strategy
        if symbol:
            clauses.append("symbol = :symbol")
            params["symbol"] = symbol
        if machine_id:
            clauses.append("machine_id = :machine_id")
            params["machine_id"] = machine_id
        if direction:
            clauses.append("direction = :direction")
            params["direction"] = direction
        if status:
            clauses.append("status = :status")
            params["status"] = status
        if since:
            clauses.append("time >= :since")
            params["since"] = since
        if until:
            clauses.append("time <= :until")
            params["until"] = until
        if not include_suspect:
            clauses.append(_SUSPECT_SQL)
        return " AND ".join(clauses)

    def list_trades(
        self,
        *,
        limit: int = 200,
        offset: int = 0,
        strategy: str | None = None,
        symbol: str | None = None,
        machine_id: str | None = None,
        direction: str | None = None,
        status: str | None = None,
        since: str | None = None,
        until: str | None = None,
        include_suspect: bool = False,
    ) -> list[dict[str, Any]]:
        if not self.configured:
            return []
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        where = self._trade_where(
            strategy=strategy,
            symbol=symbol,
            machine_id=machine_id,
            direction=direction,
            status=status,
            since=since,
            until=until,
            include_suspect=include_suspect,
            params=params,
        )
        sql = text(
            "SELECT id, envelope_id, time, strategy, machine, machine_id, broker, account, "  # noqa: S608
            "symbol, direction, action, entry, exit, quantity, pnl, latency_ms, "
            "duration_sec, status FROM trades WHERE "
            + where
            + " ORDER BY time DESC, id DESC LIMIT :limit OFFSET :offset"
        )
        with self._connect() as conn:
            rows = conn.execute(sql, params).mappings().all()
        return [self._map_trade(row) for row in rows]

    def _map_trade(self, row: Any) -> dict[str, Any]:
        return {
            "id": row["id"],
            "envelope_id": row["envelope_id"],
            "time": to_utc_z(row["time"]),
            "trade_ts": to_utc_z(row["time"]),
            "strategy": _blank_to_none(row["strategy"]),
            "machine": _blank_to_none(row["machine"]),
            "machine_id": row["machine_id"],
            "broker": _blank_to_none(row["broker"]),
            "account": _blank_to_none(row["account"]),
            "symbol": _blank_to_none(row["symbol"]),
            "direction": _blank_to_none(row["direction"]),
            "entry": row["entry"],
            "exit": row["exit"],
            "quantity": row["quantity"],
            "pnl": row["pnl"],
            "latency_ms": row["latency_ms"],
            "duration_sec": row["duration_sec"],
            "status": row["status"],
        }

    def aggregate_trade_groups(
        self,
        *,
        group_by: str,
        strategy: str | None = None,
        symbol: str | None = None,
        include_suspect: bool = False,
    ) -> list[dict[str, Any]]:
        """SQL aggregation over classified trade rows (never events)."""

        if not self.configured:
            return []
        if group_by == "strategy":
            select_dims = "NULLIF(strategy, '') AS strategy_name, machine_id"
            group_sql = "NULLIF(strategy, ''), machine_id"
        elif group_by == "strategy_symbol":
            select_dims = (
                "NULLIF(strategy, '') AS strategy_name, "
                "NULLIF(symbol, '') AS symbol, machine_id"
            )
            group_sql = "NULLIF(strategy, ''), NULLIF(symbol, ''), machine_id"
        elif group_by == "symbol_strategy":
            select_dims = (
                "NULLIF(symbol, '') AS symbol, "
                "NULLIF(strategy, '') AS strategy_name, machine_id"
            )
            group_sql = "NULLIF(symbol, ''), NULLIF(strategy, ''), machine_id"
        else:
            raise ValueError(f"unsupported group_by: {group_by}")

        params: dict[str, Any] = {}
        where = self._trade_where(
            strategy=strategy,
            symbol=symbol,
            machine_id=None,
            direction=None,
            status="closed",
            since=None,
            until=None,
            include_suspect=include_suspect,
            params=params,
        )
        sql = text(
            f"SELECT {select_dims}, "  # noqa: S608
            "COUNT(*) AS trade_count, "
            "SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) AS winning_trades, "
            "SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) AS losing_trades, "
            "SUM(pnl) AS gross_pnl, "
            "AVG(pnl) AS average_trade, "
            "MAX(pnl) AS best_trade, "
            "MIN(pnl) AS worst_trade, "
            "AVG(latency_ms) AS avg_latency_ms "
            "FROM trades WHERE "
            + where
            + f" GROUP BY {group_sql}"
        )
        with self._connect() as conn:
            rows = conn.execute(sql, params).mappings().all()
        return [dict(row) for row in rows]

    def list_system_health(
        self,
        *,
        machine_id: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        if not self.configured:
            return []
        clauses = [
            "machine_id NOT IN ('mch-london', 'mch-gcloud', 'mch-pc')",
        ]
        params: dict[str, Any] = {"limit": limit}
        if machine_id:
            slug_mid = f"mch-agent-{machine_id}" if not machine_id.startswith("mch-") else machine_id
            raw_mid = machine_id.replace("mch-agent-", "")
            clauses.append("(machine_id = :machine_id OR machine_id = :slug_mid OR machine_id = :raw_mid)")
            params["machine_id"] = machine_id
            params["slug_mid"] = slug_mid
            params["raw_mid"] = raw_mid
        if start:
            clauses.append("timestamp_utc >= :start")
            params["start"] = start
        if end:
            clauses.append("timestamp_utc <= :end")
            params["end"] = end

        where = " AND ".join(clauses)
        sql = text(
            f"""
            SELECT id, machine_id, agent_id, event_id, timestamp_utc,
                   tick_rate, tick_delay_ms, queue_size, queue_wait_ms,
                   avg_latency_ms, p95_latency_ms, p99_latency_ms,
                   api_success_pct, signal_fill_rate_pct, cpu_usage_pct,
                   memory_mb, status, created_at
            FROM (
                SELECT id, machine_id, agent_id, event_id, timestamp_utc,
                       tick_rate, tick_delay_ms, queue_size, queue_wait_ms,
                       avg_latency_ms, p95_latency_ms, p99_latency_ms,
                       api_success_pct, signal_fill_rate_pct, cpu_usage_pct,
                       memory_mb, status, created_at
                FROM system_health_snapshots
                WHERE {where}
                ORDER BY timestamp_utc DESC
                LIMIT :limit
            ) sub
            ORDER BY timestamp_utc ASC
            """
        )
        with self._connect() as conn:
            rows = conn.execute(sql, params).mappings().all()
        return [
            {
                "id": row["id"],
                "machine_id": row["machine_id"],
                "agent_id": _blank_to_none(row["agent_id"]),
                "event_id": _blank_to_none(row["event_id"]),
                "timestamp": to_utc_z(row["timestamp_utc"]),
                "generated_at": to_utc_z(row["timestamp_utc"]),
                "tick_rate": row["tick_rate"],
                "tick_delay_ms": row["tick_delay_ms"],
                "queue_size": row["queue_size"],
                "queue_wait_ms": row["queue_wait_ms"],
                "avg_latency_ms": row["avg_latency_ms"],
                "p95_latency_ms": row["p95_latency_ms"],
                "p99_latency_ms": row["p99_latency_ms"],
                "api_success_pct": row["api_success_pct"],
                "api_success_rate": row["api_success_pct"],
                "signal_fill_rate_pct": row["signal_fill_rate_pct"],
                "signal_fill_rate": row["signal_fill_rate_pct"],
                "cpu_usage_pct": row["cpu_usage_pct"],
                "cpu_usage": row["cpu_usage_pct"],
                "memory_mb": row["memory_mb"],
                "status": row["status"],
                "created_at": to_utc_z(row["created_at"]),
                "received_at": to_utc_z(row["created_at"]),
            }
            for row in rows
        ]
