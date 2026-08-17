"""PostgreSQL-backed repositories for the five persisted telemetry entities.

These mirror the in-memory repositories' method surface *exactly* (``list``,
``get``, ``upsert``, ``update``, ``prepend``, ``by_source``, ``insert``) and
return the same dict shapes, so routers, services and the websocket layer are
unchanged. The store is selected at import time in ``app/repositories`` based on
``DATABASE_URL``.

Transaction model
-----------------
* ``unit_of_work()`` opens one transaction per ingested envelope (used by the
  agent service). Repo writes/reads enlist in that transaction via a ContextVar,
  so the dedup-reserve + all derived rows commit atomically.
* Calls made outside a unit of work (router reads, the publisher) get their own
  short-lived session.

Idempotency
-----------
``reserve_envelope()`` inserts the envelope id into ``ingest_dedup`` with
``ON CONFLICT DO NOTHING``; a no-op insert means the envelope was already
processed, so the whole dispatch is skipped. Each row additionally carries the
``envelope_id`` under a unique index as defense in depth.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
from typing import Any, Iterator, Optional

from sqlalchemy import Table, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.session import database_enabled, get_sessionmaker
from app.models import (
    DeadLetter,
    EodDataset,
    EodDatasetFile,
    Event,
    IngestDedup,
    Log,
    Machine,
    Metric,
    QuantReport,
    SyncState,
    TradingSession,
    Trade,
    utcnow,
)
from app.models.dead_letter import PAYLOAD_PREVIEW_LIMIT

# Read caps mirror the old in-memory bounds so router `[:limit]` slicing is
# identical and we never scan an unbounded table for a feed.
EVENTS_CAP = 400
LOGS_CAP = 1000
TRADES_CAP = 1000

# Fallbacks used only if Settings cannot be loaded (for import-time unit tests).
DEFAULT_DEGRADED_AFTER_SEC = 30.0
DEFAULT_OFFLINE_AFTER_SEC = 120.0


# --------------------------------------------------------------------------- #
# Unit of work / session plumbing
# --------------------------------------------------------------------------- #
_uow: ContextVar[Optional[Session]] = ContextVar("raj_uow", default=None)


@contextmanager
def unit_of_work() -> Iterator[Optional[Session]]:
    """One transaction per envelope. No-op (yields None) in mock mode."""
    if not database_enabled():
        yield None
        return
    session = get_sessionmaker()()
    token = _uow.set(session)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        _uow.reset(token)
        session.close()


@contextmanager
def _write_session() -> Iterator[Session]:
    """Yield the active UoW session, or a self-committing short-lived one."""
    existing = _uow.get()
    if existing is not None:
        yield existing
        return
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def _read_session() -> Iterator[Session]:
    """Reads enlist in the UoW (to see its uncommitted writes) or open their own."""
    existing = _uow.get()
    if existing is not None:
        yield existing
        return
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def _insert_ignore(session: Session, table: Table, values: dict[str, Any], index_elements: list[str]):
    """Dialect-aware ``INSERT … ON CONFLICT DO NOTHING``; returns the result."""
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as _insert
        stmt = _insert(table).values(**values).on_conflict_do_nothing(index_elements=index_elements)
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as _insert
        stmt = _insert(table).values(**values).on_conflict_do_nothing(index_elements=index_elements)
    else:  # pragma: no cover - other backends fall back to a plain insert
        stmt = table.insert().values(**values)
    return session.execute(stmt)


def reserve_envelope(envelope_id: str | None, kind: str) -> bool:
    """Reserve an envelope id for processing.

    Returns True if this is the first time we've seen it (process it), False if
    it was already processed (skip). Envelopes without an id can't be deduped, so
    they are always processed.
    """
    if not database_enabled() or not envelope_id:
        return True
    session = _uow.get()
    if session is not None:
        res = _insert_ignore(session, IngestDedup.__table__,
                             {"envelope_id": envelope_id, "kind": kind}, ["envelope_id"])
        return res.rowcount != 0
    with _write_session() as s:
        res = _insert_ignore(s, IngestDedup.__table__,
                             {"envelope_id": envelope_id, "kind": kind}, ["envelope_id"])
        return res.rowcount != 0


# --------------------------------------------------------------------------- #
# Serialization helpers (ORM -> the existing dict shapes)
# --------------------------------------------------------------------------- #
def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _iso(dt: datetime | None) -> str | None:
    """UTC ISO-8601 with a Z suffix. None stays None (unknown, not epoch)."""
    if dt is None:
        return None
    aware = _aware(dt).astimezone(timezone.utc)
    return aware.isoformat().replace("+00:00", "Z")


def _parse_iso(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return utcnow()


def derive_machine_status(
    stored_status: str,
    python_status: str,
    last_heartbeat: datetime | None,
    *,
    live: bool,
    now: datetime | None = None,
    degraded_after_seconds: float | None = None,
    offline_after_seconds: float | None = None,
) -> tuple[str, str]:
    """Derive visible machine/runtime status from heartbeat age.

    AWS never fabricates liveness. A live machine with no heartbeat is
    ``unknown``; after the configurable degraded/offline thresholds it degrades
    and then becomes offline. Non-live seeded/demo rows keep their stored state.
    """
    if not live:
        return stored_status, python_status
    if last_heartbeat is None:
        return "unknown", "unknown"

    degraded_after = (
        DEFAULT_DEGRADED_AFTER_SEC
        if degraded_after_seconds is None
        else float(degraded_after_seconds)
    )
    offline_after = (
        DEFAULT_OFFLINE_AFTER_SEC
        if offline_after_seconds is None
        else float(offline_after_seconds)
    )
    now = now or utcnow()
    age = max(0.0, (_aware(now) - _aware(last_heartbeat)).total_seconds())
    if age > offline_after:
        return "offline", "offline"
    if age > degraded_after:
        return "degraded", "degraded"
    return stored_status, python_status


def _machine_to_dict(m: Machine, now: datetime) -> dict[str, Any]:
    settings = get_settings()
    status, py_status = derive_machine_status(
        m.status,
        m.python_status,
        m.last_heartbeat,
        live=m.live,
        now=now,
        degraded_after_seconds=settings.heartbeat_degraded_after_seconds,
        offline_after_seconds=settings.heartbeat_offline_after_seconds,
    )
    return {
        "id": m.id, "name": m.name, "location": m.location, "provider": m.provider,
        "status": status, "cpu": m.cpu, "ram": m.ram, "disk": m.disk,
        "temperatureC": m.temperature_c, "internetMs": m.internet_ms,
        "brokerPingMs": m.broker_ping_ms, "pythonStatus": py_status,
        "uptimeSec": m.uptime_sec, "lastHeartbeat": _iso(m.last_heartbeat),
        "strategyCount": m.strategy_count, "agentId": m.agent_id,
        "agentVersion": m.agent_version, "hostname": m.hostname or m.name,
        "environment": m.environment or None, "lastEvent": _iso(m.last_event),
        "lastTrade": _iso(m.last_trade), "lastError": _iso(m.last_error),
        "lastSuccessfulUpload": _iso(m.last_successful_upload),
        "queueDepth": m.queue_depth, "oldestPendingAgeSec": m.oldest_pending_age_sec,
        "transportState": m.transport_state, "currentSessionId": m.current_session_id,
        "tradingProcessState": m.trading_process_state, "lastEodSync": _iso(m.last_eod_sync),
        "lastEodStatus": m.last_eod_status, "recoveryState": m.recovery_state,
        "lastRecovery": _iso(m.last_recovery_at), "eventsRecovered": m.events_recovered,
        "eodBacklog": m.eod_backlog,
    }


def _event_to_dict(e: Event) -> dict[str, Any]:
    return {"id": e.id, "time": _iso(e.time), "category": e.category,
            "severity": e.severity, "source": e.source, "message": e.message,
            "machineId": e.machine_id, "eventType": e.event_type,
            "strategy": e.strategy, "symbol": e.symbol, "sessionId": e.session_id,
            "sequenceId": e.sequence_id, "payloadSummary": e.payload_summary,
            "receivedAt": _iso(e.created_at)}


def _log_to_dict(row: Log) -> dict[str, Any]:
    return {"id": row.id, "time": _iso(row.time), "source": row.source,
            "level": row.level, "logger": row.logger, "message": row.message}


def _trade_to_dict(t: Trade) -> dict[str, Any]:
    return {
        "id": t.id, "time": _iso(t.time), "strategy": t.strategy, "machine": t.machine,
        "broker": t.broker, "account": t.account, "symbol": t.symbol,
        "direction": t.direction, "entry": t.entry, "exit": t.exit,
        "quantity": t.quantity, "pnl": t.pnl, "latencyMs": t.latency_ms,
        "durationSec": t.duration_sec, "status": t.status,
    }


# camelCase input dict (as built by agent_service) -> Machine column kwargs.
_MACHINE_KEY_MAP = {
    "id": "id", "name": "name", "location": "location", "provider": "provider",
    "status": "status", "cpu": "cpu", "ram": "ram", "disk": "disk",
    "temperatureC": "temperature_c", "internetMs": "internet_ms",
    "brokerPingMs": "broker_ping_ms", "pythonStatus": "python_status",
    "uptimeSec": "uptime_sec", "strategyCount": "strategy_count",
    "lastHeartbeat": "last_heartbeat", "live": "live", "agentId": "agent_id",
    "agentVersion": "agent_version", "hostname": "hostname", "environment": "environment",
    "lastEvent": "last_event", "lastTrade": "last_trade", "lastError": "last_error",
    "lastSuccessfulUpload": "last_successful_upload", "queueDepth": "queue_depth",
    "oldestPendingAgeSec": "oldest_pending_age_sec", "transportState": "transport_state",
    "currentSessionId": "current_session_id", "tradingProcessState": "trading_process_state",
    "lastEodSync": "last_eod_sync", "lastEodStatus": "last_eod_status",
    "recoveryState": "recovery_state", "lastRecovery": "last_recovery_at",
    "eventsRecovered": "events_recovered", "eodBacklog": "eod_backlog",
}


def _to_machine_columns(d: dict[str, Any]) -> dict[str, Any]:
    cols: dict[str, Any] = {}
    for key, col in _MACHINE_KEY_MAP.items():
        if key not in d:
            continue
        cols[col] = (
            _parse_iso(d[key])
            if col in {
                "last_heartbeat", "last_event", "last_trade", "last_error",
                "last_successful_upload", "last_eod_sync", "last_recovery_at",
            }
            else d[key]
        )
    return cols


# --------------------------------------------------------------------------- #
# Repositories
# --------------------------------------------------------------------------- #
class SqlMachinesRepository:
    def list(self) -> list[dict]:
        now = utcnow()
        with _read_session() as s:
            rows = s.execute(select(Machine).order_by(Machine.created_at, Machine.id)).scalars().all()
            return [_machine_to_dict(m, now) for m in rows]

    def get(self, machine_id: str) -> dict | None:
        with _read_session() as s:
            m = s.get(Machine, machine_id)
            return _machine_to_dict(m, utcnow()) if m is not None else None

    def upsert(self, machine: dict) -> dict:
        cols = _to_machine_columns(machine)
        mid = cols.get("id") or machine.get("id")
        with _write_session() as s:
            obj = s.get(Machine, mid)
            if obj is None:
                obj = Machine(**cols)
                s.add(obj)
            else:
                for key, val in cols.items():
                    if key != "id":
                        setattr(obj, key, val)
            s.flush()
            return _machine_to_dict(obj, utcnow())

    def update(self, machine_id: str, changes: dict) -> dict | None:
        cols = _to_machine_columns(changes)
        with _write_session() as s:
            obj = s.get(Machine, machine_id)
            if obj is None:
                return None
            for key, val in cols.items():
                if key != "id":
                    setattr(obj, key, val)
            s.flush()
            return _machine_to_dict(obj, utcnow())


class SqlEventsRepository:
    def list(self) -> list[dict]:
        return self.query(limit=EVENTS_CAP)

    def query(
        self,
        *,
        limit: int = EVENTS_CAP,
        machine_id: str | None = None,
        session_id: str | None = None,
        event_type: str | None = None,
        strategy: str | None = None,
        symbol: str | None = None,
        severity: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[dict]:
        with _read_session() as s:
            stmt = select(Event)
            if machine_id:
                stmt = stmt.where(Event.machine_id == machine_id)
            if session_id:
                stmt = stmt.where(Event.session_id == session_id)
            if event_type:
                stmt = stmt.where(Event.event_type == event_type)
            if strategy:
                stmt = stmt.where(Event.strategy == strategy)
            if symbol:
                stmt = stmt.where(Event.symbol == symbol)
            if severity:
                stmt = stmt.where(Event.severity == severity)
            if since:
                stmt = stmt.where(Event.time >= since)
            if until:
                stmt = stmt.where(Event.time <= until)
            rows = s.execute(
                stmt.order_by(Event.time.desc(), Event.id.desc()).limit(limit)
            ).scalars().all()
            return [_event_to_dict(e) for e in rows]

    def get(self, event_id: str) -> dict | None:
        with _read_session() as s:
            e = s.get(Event, event_id)
            return _event_to_dict(e) if e is not None else None

    def prepend(self, event: dict) -> None:
        with _write_session() as s:
            _insert_ignore(s, Event.__table__, {
                "id": event["id"], "envelope_id": event.get("envelope_id"),
                "time": _parse_iso(event["time"]), "category": event["category"],
                "severity": event["severity"], "source": event["source"],
                "message": event["message"], "machine_id": event.get("machine_id"),
                "event_type": event.get("event_type"), "strategy": event.get("strategy"),
                "symbol": event.get("symbol"), "session_id": event.get("session_id"),
                "sequence_id": event.get("sequence_id"),
                "payload_summary": event.get("payload_summary"),
            }, ["envelope_id"])


class SqlLogsRepository:
    def by_source(self, source: str | None) -> list[dict]:
        with _read_session() as s:
            stmt = select(Log).order_by(Log.time.desc(), Log.id.desc()).limit(LOGS_CAP)
            if source:
                stmt = (
                    select(Log).where(Log.source == source)
                    .order_by(Log.time.desc(), Log.id.desc()).limit(LOGS_CAP)
                )
            rows = s.execute(stmt).scalars().all()
            return [_log_to_dict(row) for row in rows]

    def list(self) -> list[dict]:
        return self.by_source(None)

    def prepend(self, entry: dict) -> None:
        with _write_session() as s:
            _insert_ignore(s, Log.__table__, {
                "id": entry["id"], "envelope_id": entry.get("envelope_id"),
                "time": _parse_iso(entry["time"]), "source": entry["source"],
                "level": entry["level"], "logger": entry["logger"],
                "message": entry["message"], "machine_id": entry.get("machine_id"),
            }, ["envelope_id"])


class SqlTradesRepository:
    def list(self) -> list[dict]:
        with _read_session() as s:
            rows = s.execute(
                select(Trade).order_by(Trade.time.desc(), Trade.id.desc()).limit(TRADES_CAP)
            ).scalars().all()
            return [_trade_to_dict(t) for t in rows]

    def get(self, trade_id: str) -> dict | None:
        with _read_session() as s:
            t = s.get(Trade, trade_id)
            return _trade_to_dict(t) if t is not None else None

    def insert(self, trade: dict) -> None:
        with _write_session() as s:
            _insert_ignore(s, Trade.__table__, {
                "id": trade["id"], "envelope_id": trade.get("envelope_id"),
                "time": _parse_iso(trade["time"]), "strategy": trade.get("strategy", ""),
                "machine": trade.get("machine", ""), "machine_id": trade.get("machine_id"),
                "broker": trade.get("broker", ""), "account": trade.get("account", ""),
                "symbol": trade.get("symbol", ""), "direction": trade.get("direction", "long"),
                "action": trade.get("action"), "entry": float(trade.get("entry", 0.0) or 0.0),
                "exit": trade.get("exit"), "quantity": float(trade.get("quantity", 0.0) or 0.0),
                "pnl": float(trade.get("pnl", 0.0) or 0.0),
                "latency_ms": float(trade.get("latencyMs", 0.0) or 0.0),
                "duration_sec": int(trade.get("durationSec", 0) or 0),
                "status": trade.get("status", "closed"),
            }, ["envelope_id"])


class SqlMetricsRepository:
    def insert(self, metric: dict) -> None:
        with _write_session() as s:
            _insert_ignore(s, Metric.__table__, {
                "envelope_id": metric.get("envelope_id"),
                "time": _parse_iso(metric["time"]), "machine": metric.get("machine", ""),
                "machine_id": metric.get("machine_id"), "strategy": metric.get("strategy"),
                "name": metric["name"], "value": float(metric.get("value", 0.0) or 0.0),
                "unit": metric.get("unit"),
            }, ["envelope_id", "name"])

    def list(self) -> list[dict]:
        with _read_session() as s:
            rows = s.execute(select(Metric).order_by(Metric.time.desc()).limit(LOGS_CAP)).scalars().all()
            return [{"time": _iso(m.time), "machine": m.machine, "strategy": m.strategy,
                     "name": m.name, "value": m.value, "unit": m.unit} for m in rows]


class SqlSyncStateRepository:
    """Per-(machine, agent) delivery bookkeeping.

    ``record_batch`` is called once per batch, outside the per-envelope units of
    work, so a rolled-back envelope never erases the fact that a batch arrived.
    """

    def get(self, machine_id: str, agent_id: str) -> dict | None:
        with _read_session() as s:
            row = s.execute(
                select(SyncState).where(
                    SyncState.machine_id == machine_id, SyncState.agent_id == agent_id
                )
            ).scalar_one_or_none()
            return _sync_state_to_dict(row) if row is not None else None

    @staticmethod
    def _acquire(session: Session, machine_id: str, machine: str, agent_id: str) -> SyncState:
        """Fetch this agent's row, creating it if absent.

        Two batches from one agent can be in flight at once (FastAPI serves them
        concurrently), so the create path races: both could see no row and both
        insert, tripping ``uq_sync_state_machine_agent``. ``SELECT … FOR UPDATE``
        does not help here because there is no row to lock yet — so the insert is
        attempted and a unique-violation is resolved by re-reading the row the
        other request just committed.
        """
        stmt = select(SyncState).where(
            SyncState.machine_id == machine_id, SyncState.agent_id == agent_id
        )
        if session.get_bind().dialect.name == "postgresql":
            # Serialise concurrent updates to an existing row.
            stmt = stmt.with_for_update()
        row = session.execute(stmt).scalar_one_or_none()
        if row is not None:
            return row

        row = SyncState(machine_id=machine_id, machine=machine, agent_id=agent_id)
        session.add(row)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            row = session.execute(stmt).scalar_one_or_none()
            if row is None:  # pragma: no cover - the constraint fired, so it exists
                raise
        return row

    def record_batch(
        self,
        *,
        machine_id: str,
        machine: str,
        agent_id: str,
        max_sequence_id: int | None,
        last_event_time: datetime | None,
        queue_depth: int | None,
        accepted: int,
        duplicate: int,
        failed: int,
        session_id: str | None,
    ) -> dict:
        """Fold one batch's results into the row, returning its new state.

        Gap detection compares this batch's lowest new sequence number against
        the highest previously seen. A gap is *recorded*, never a rejection —
        the missing envelopes may still arrive on a later retry, and refusing
        valid data because earlier data is late would turn a small loss into a
        large one.
        """
        now = utcnow()
        with _write_session() as s:
            row = self._acquire(s, machine_id, machine, agent_id)

            row.machine = machine or row.machine
            row.last_batch_at = now
            row.last_ack_at = now
            if queue_depth is not None:
                row.queue_depth = int(queue_depth)
            if session_id:
                row.session_id = session_id
            if last_event_time is not None and (
                row.last_event_time is None or last_event_time > _aware(row.last_event_time)
            ):
                row.last_event_time = last_event_time

            row.accepted_count = (row.accepted_count or 0) + accepted
            row.duplicate_count = (row.duplicate_count or 0) + duplicate
            row.failed_count = (row.failed_count or 0) + failed

            if max_sequence_id is not None:
                previous = row.last_sequence_id
                if previous is not None and max_sequence_id > previous + 1:
                    # Numbers between `previous` and `max_sequence_id` never arrived.
                    row.gap_count = (row.gap_count or 0) + 1
                    row.last_gap_from = previous + 1
                    row.last_gap_to = max_sequence_id - 1
                    row.last_gap_at = now
                    row.missing_count = (row.missing_count or 0) + (max_sequence_id - previous - 1)
                if previous is None or max_sequence_id > previous:
                    row.last_sequence_id = max_sequence_id
            s.flush()
            return _sync_state_to_dict(row)

    def list(self) -> list[dict]:
        with _read_session() as s:
            rows = s.execute(
                select(SyncState).order_by(SyncState.last_batch_at.desc().nullslast())
            ).scalars().all()
            return [_sync_state_to_dict(r) for r in rows]


class SqlSessionsRepository:
    """Trading sessions, created lazily from whatever the agent reports."""

    def touch(
        self,
        *,
        session_id: str,
        machine_id: str,
        machine: str,
        event_time: datetime | None,
        is_trade: bool = False,
    ) -> None:
        with _write_session() as s:
            row = s.execute(
                select(TradingSession).where(
                    TradingSession.session_id == session_id,
                    TradingSession.machine_id == machine_id,
                )
            ).scalar_one_or_none()
            if row is None:
                row = TradingSession(
                    session_id=session_id, machine_id=machine_id, machine=machine,
                    status="open", started_at=event_time,
                )
                s.add(row)
                s.flush()
            row.event_count = (row.event_count or 0) + 1
            if is_trade:
                row.trade_count = (row.trade_count or 0) + 1
            if event_time is not None and (
                row.last_event_at is None or event_time > _aware(row.last_event_at)
            ):
                row.last_event_at = event_time

    def close(self, *, session_id: str, machine_id: str, ended_at: datetime | None) -> None:
        with _write_session() as s:
            row = s.execute(
                select(TradingSession).where(
                    TradingSession.session_id == session_id,
                    TradingSession.machine_id == machine_id,
                )
            ).scalar_one_or_none()
            if row is None:
                return
            row.status = "closed"
            row.ended_at = ended_at or utcnow()

    def latest(self, machine_id: str) -> dict | None:
        with _read_session() as s:
            row = s.execute(
                select(TradingSession)
                .where(TradingSession.machine_id == machine_id)
                .order_by(TradingSession.last_event_at.desc().nullslast())
                .limit(1)
            ).scalar_one_or_none()
            return _session_to_dict(row) if row is not None else None

    def get(self, session_id: str, *, machine_id: str | None = None) -> dict | None:
        with _read_session() as s:
            stmt = select(TradingSession).where(TradingSession.session_id == session_id)
            if machine_id:
                stmt = stmt.where(TradingSession.machine_id == machine_id)
            row = s.execute(
                stmt.order_by(TradingSession.last_event_at.desc().nullslast()).limit(1)
            ).scalar_one_or_none()
            return _session_to_dict(row) if row is not None else None

    def list(
        self,
        *,
        limit: int = 100,
        machine_id: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        with _read_session() as s:
            stmt = select(TradingSession)
            if machine_id:
                stmt = stmt.where(TradingSession.machine_id == machine_id)
            if status:
                stmt = stmt.where(TradingSession.status == status)
            rows = s.execute(
                stmt.order_by(TradingSession.last_event_at.desc().nullslast())
                .limit(min(limit, EVENTS_CAP))
            ).scalars().all()
            return [_session_to_dict(r) for r in rows]


class SqlDeadLetterRepository:
    """Durable record of permanently unprocessable envelopes."""

    def insert(self, entry: dict) -> None:
        preview = entry.get("payload_preview")
        if preview is not None:
            preview = str(preview)[:PAYLOAD_PREVIEW_LIMIT]
        # Deliberately its own short-lived session: a dead letter must survive
        # even when the envelope's own unit of work is being rolled back.
        with _write_session() as s:
            s.add(DeadLetter(
                envelope_id=entry.get("envelope_id"), kind=entry.get("kind"),
                machine=entry.get("machine"), machine_id=entry.get("machine_id"),
                agent_id=entry.get("agent_id"), strategy=entry.get("strategy"),
                sequence_id=entry.get("sequence_id"), reason=str(entry.get("reason", "unknown")),
                error_type=entry.get("error_type"), payload_preview=preview,
            ))

    def list(self) -> list[dict]:
        with _read_session() as s:
            rows = s.execute(
                select(DeadLetter).order_by(DeadLetter.received_at.desc()).limit(LOGS_CAP)
            ).scalars().all()
            return [{
                "id": r.id, "envelopeId": r.envelope_id, "kind": r.kind,
                "machine": r.machine, "machineId": r.machine_id, "agentId": r.agent_id,
                "strategy": r.strategy, "sequenceId": r.sequence_id, "reason": r.reason,
                "errorType": r.error_type, "receivedAt": _iso(r.received_at),
            } for r in rows]


def prune_dedup(retention_days: int) -> int:
    """Delete idempotency rows older than the retention window.

    ``ingest_dedup`` grows by one row per envelope forever otherwise. The window
    must exceed the agent's longest realistic offline period, since an envelope
    replayed after its dedup row is pruned would be processed a second time.
    """
    if not database_enabled() or retention_days <= 0:
        return 0
    from datetime import timedelta
    cutoff = utcnow() - timedelta(days=retention_days)
    with _write_session() as s:
        result = s.execute(
            IngestDedup.__table__.delete().where(IngestDedup.__table__.c.processed_at < cutoff)
        )
        return int(result.rowcount or 0)


def _sync_state_to_dict(row: SyncState) -> dict[str, Any]:
    return {
        "machineId": row.machine_id, "machine": row.machine, "agentId": row.agent_id,
        "lastSequenceId": row.last_sequence_id,
        "lastEventTime": _iso(row.last_event_time),
        "lastBatchAt": _iso(row.last_batch_at), "lastAckAt": _iso(row.last_ack_at),
        "queueDepth": row.queue_depth, "gapCount": row.gap_count,
        "missingCount": row.missing_count,
        "lastGapFrom": row.last_gap_from, "lastGapTo": row.last_gap_to,
        "lastGapAt": _iso(row.last_gap_at),
        "acceptedCount": row.accepted_count, "duplicateCount": row.duplicate_count,
        "failedCount": row.failed_count, "sessionId": row.session_id,
    }


def _session_to_dict(row: TradingSession) -> dict[str, Any]:
    return {
        "sessionId": row.session_id, "machineId": row.machine_id, "machine": row.machine,
        "status": row.status, "startedAt": _iso(row.started_at), "endedAt": _iso(row.ended_at),
        "lastEventAt": _iso(row.last_event_at), "eventCount": row.event_count,
        "tradeCount": row.trade_count,
    }


def _eod_file_to_dict(row: EodDatasetFile) -> dict[str, Any]:
    return {
        "fileId": row.file_id,
        "relativePath": row.relative_path,
        "datasetType": row.dataset_type,
        "sizeBytes": row.size_bytes,
        "sha256": row.sha256,
        "rowCount": row.row_count,
        "storageKey": row.storage_key,
        "bytesReceived": row.bytes_received,
        "status": row.status,
        "checksumStatus": row.checksum_status,
        "failureReason": row.failure_reason,
        "uploadedAt": _iso(row.uploaded_at) or None,
        "validatedAt": _iso(row.validated_at) or None,
    }


def _eod_dataset_to_dict(row: EodDataset, files: list[EodDatasetFile] | None = None) -> dict[str, Any]:
    return {
        "datasetId": row.dataset_id,
        "machineId": row.machine_id,
        "machine": row.machine,
        "agentId": row.agent_id,
        "sessionId": row.session_id,
        "tradingDate": row.trading_date,
        "schemaVersion": row.schema_version,
        "manifestCreatedAt": _iso(row.manifest_created_at) or None,
        "status": row.status,
        "statusReason": row.status_reason,
        "storageBackend": row.storage_backend,
        "totalFiles": row.total_files,
        "uploadedFiles": row.uploaded_files,
        "totalBytes": row.total_bytes,
        "uploadedBytes": row.uploaded_bytes,
        "completedAt": _iso(row.completed_at) or None,
        "finalizedAt": _iso(row.finalized_at) or None,
        "rawDeletedAt": _iso(row.raw_deleted_at) or None,
        "receivedAt": _iso(row.received_at),
        "updatedAt": _iso(row.updated_at),
        "files": [_eod_file_to_dict(file) for file in files] if files is not None else [],
    }


def _json_load(text: str, fallback: Any) -> Any:
    try:
        return json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _quant_report_to_dict(row: QuantReport) -> dict[str, Any]:
    return {
        "reportId": row.report_id,
        "datasetId": row.dataset_id,
        "machineId": row.machine_id,
        "tradingDate": row.trading_date,
        "status": row.status,
        "coverage": _json_load(row.coverage_json, {}),
        "tradeMetrics": _json_load(row.trade_metrics_json, {}),
        "marketReplay": _json_load(row.market_replay_json, {}),
        "analytics": _json_load(row.analytics_json, {}),
        "warnings": _json_load(row.warnings_json, []),
        "createdAt": _iso(row.created_at),
        "updatedAt": _iso(row.updated_at),
    }


class SqlEodRepository:
    """Durable EOD manifest/upload catalog."""

    def get(self, dataset_id: str, *, include_files: bool = True) -> dict | None:
        with _read_session() as s:
            row = s.get(EodDataset, dataset_id)
            if row is None:
                return None
            files = self._files(s, dataset_id) if include_files else None
            return _eod_dataset_to_dict(row, files)

    def list(
        self,
        *,
        limit: int = 100,
        status: str | None = None,
        machine_id: str | None = None,
        trading_date: str | None = None,
    ) -> list[dict]:
        with _read_session() as s:
            stmt = select(EodDataset)
            if status:
                stmt = stmt.where(EodDataset.status == status)
            if machine_id:
                stmt = stmt.where(EodDataset.machine_id == machine_id)
            if trading_date:
                stmt = stmt.where(EodDataset.trading_date == trading_date)
            rows = s.execute(
                stmt.order_by(EodDataset.received_at.desc(), EodDataset.dataset_id.desc()).limit(limit)
            ).scalars().all()
            return [_eod_dataset_to_dict(row, None) for row in rows]

    def create(self, dataset: dict[str, Any], files: list[dict[str, Any]]) -> dict:
        with _write_session() as s:
            row = EodDataset(
                dataset_id=dataset["datasetId"],
                machine_id=dataset["machineId"],
                machine=dataset["machine"],
                agent_id=dataset["agentId"],
                session_id=dataset.get("sessionId"),
                trading_date=dataset["tradingDate"],
                schema_version=str(dataset.get("schemaVersion", "1")),
                manifest_created_at=_parse_iso(dataset.get("manifestCreatedAt")),
                status=dataset.get("status", "MANIFESTED"),
                status_reason=dataset.get("statusReason"),
                storage_backend=dataset.get("storageBackend", "local"),
                total_files=len(files),
                total_bytes=sum(int(file.get("sizeBytes", 0)) for file in files),
            )
            s.add(row)
            for file in files:
                s.add(EodDatasetFile(
                    dataset_id=row.dataset_id,
                    file_id=file["fileId"],
                    relative_path=file["relativePath"],
                    dataset_type=file["datasetType"],
                    size_bytes=int(file["sizeBytes"]),
                    sha256=str(file["sha256"]).lower(),
                    row_count=file.get("rowCount"),
                    storage_key=file.get("storageKey"),
                ))
            s.flush()
            return _eod_dataset_to_dict(row, self._files(s, row.dataset_id))

    def update_dataset(self, dataset_id: str, changes: dict[str, Any]) -> dict | None:
        with _write_session() as s:
            row = s.get(EodDataset, dataset_id)
            if row is None:
                return None
            self._apply_dataset_changes(row, changes)
            s.flush()
            return _eod_dataset_to_dict(row, self._files(s, dataset_id))

    def get_file(self, dataset_id: str, file_id: str) -> dict | None:
        with _read_session() as s:
            row = self._file(s, dataset_id, file_id)
            return _eod_file_to_dict(row) if row is not None else None

    def update_file(self, dataset_id: str, file_id: str, changes: dict[str, Any]) -> dict | None:
        with _write_session() as s:
            file = self._file(s, dataset_id, file_id)
            if file is None:
                return None
            self._apply_file_changes(file, changes)
            self._recalculate_dataset(s, dataset_id)
            s.flush()
            return _eod_file_to_dict(file)

    def reconciliation(self) -> dict[str, Any]:
        with _read_session() as s:
            datasets = s.execute(select(EodDataset)).scalars().all()
            files = s.execute(select(EodDatasetFile)).scalars().all()
            by_status: dict[str, int] = {}
            for dataset in datasets:
                by_status[dataset.status] = by_status.get(dataset.status, 0) + 1
            return {
                "total": len(datasets),
                "byStatus": by_status,
                "missingFiles": sum(1 for file in files if file.bytes_received < file.size_bytes),
                "failedFiles": sum(1 for file in files if file.status in {"FAILED", "CONFLICT"}),
                "checksumFailures": sum(1 for file in files if file.checksum_status == "FAILED"),
                "partialDatasets": sum(1 for dataset in datasets if dataset.status in {"PARTIAL", "UPLOADING"}),
            }

    @staticmethod
    def _files(session: Session, dataset_id: str) -> list[EodDatasetFile]:
        return list(
            session.execute(
                select(EodDatasetFile)
                .where(EodDatasetFile.dataset_id == dataset_id)
                .order_by(EodDatasetFile.relative_path)
            ).scalars().all()
        )

    @staticmethod
    def _file(session: Session, dataset_id: str, file_id: str) -> EodDatasetFile | None:
        return session.execute(
            select(EodDatasetFile).where(
                EodDatasetFile.dataset_id == dataset_id,
                EodDatasetFile.file_id == file_id,
            )
        ).scalar_one_or_none()

    @staticmethod
    def _apply_dataset_changes(row: EodDataset, changes: dict[str, Any]) -> None:
        mapping = {
            "status": "status",
            "statusReason": "status_reason",
            "uploadedFiles": "uploaded_files",
            "uploadedBytes": "uploaded_bytes",
            "completedAt": "completed_at",
            "finalizedAt": "finalized_at",
            "rawDeletedAt": "raw_deleted_at",
        }
        for key, attr in mapping.items():
            if key not in changes:
                continue
            value = changes[key]
            setattr(
                row,
                attr,
                _parse_iso(value)
                if attr in {"completed_at", "finalized_at", "raw_deleted_at"}
                else value,
            )

    @staticmethod
    def _apply_file_changes(row: EodDatasetFile, changes: dict[str, Any]) -> None:
        mapping = {
            "storageKey": "storage_key",
            "bytesReceived": "bytes_received",
            "status": "status",
            "checksumStatus": "checksum_status",
            "failureReason": "failure_reason",
            "uploadedAt": "uploaded_at",
            "validatedAt": "validated_at",
        }
        for key, attr in mapping.items():
            if key not in changes:
                continue
            value = changes[key]
            setattr(row, attr, _parse_iso(value) if attr in {"uploaded_at", "validated_at"} else value)

    def _recalculate_dataset(self, session: Session, dataset_id: str) -> None:
        row = session.get(EodDataset, dataset_id)
        if row is None:
            return
        files = self._files(session, dataset_id)
        row.total_files = len(files)
        row.total_bytes = sum(file.size_bytes for file in files)
        row.uploaded_files = sum(1 for file in files if file.status in {"READY", "COMPLETE"})
        row.uploaded_bytes = sum(file.bytes_received for file in files)


class SqlQuantReportRepository:
    """Durable quant report read model."""

    def list(self, *, limit: int = 100, dataset_id: str | None = None) -> list[dict[str, Any]]:
        with _read_session() as s:
            stmt = select(QuantReport)
            if dataset_id:
                stmt = stmt.where(QuantReport.dataset_id == dataset_id)
            rows = s.execute(
                stmt.order_by(QuantReport.updated_at.desc(), QuantReport.report_id.desc()).limit(limit)
            ).scalars().all()
            return [_quant_report_to_dict(row) for row in rows]

    def get(self, report_id: str) -> dict[str, Any] | None:
        with _read_session() as s:
            row = s.get(QuantReport, report_id)
            return _quant_report_to_dict(row) if row is not None else None

    def latest_for_dataset(self, dataset_id: str) -> dict[str, Any] | None:
        rows = self.list(limit=1, dataset_id=dataset_id)
        return rows[0] if rows else None

    def upsert(self, report: dict[str, Any]) -> dict[str, Any]:
        now = utcnow()
        payload = {
            "coverage_json": json.dumps(report["coverage"], sort_keys=True),
            "trade_metrics_json": json.dumps(report["tradeMetrics"], sort_keys=True),
            "market_replay_json": json.dumps(report["marketReplay"], sort_keys=True),
            "analytics_json": json.dumps(report.get("analytics", {}), sort_keys=True),
            "warnings_json": json.dumps(report.get("warnings", []), sort_keys=True),
        }
        with _write_session() as s:
            row = s.get(QuantReport, report["reportId"])
            if row is None:
                row = QuantReport(
                    report_id=report["reportId"],
                    dataset_id=report["datasetId"],
                    machine_id=report["machineId"],
                    trading_date=report["tradingDate"],
                    status=report["status"],
                    created_at=now,
                    updated_at=now,
                    **payload,
                )
                s.add(row)
            else:
                row.dataset_id = report["datasetId"]
                row.machine_id = report["machineId"]
                row.trading_date = report["tradingDate"]
                row.status = report["status"]
                row.coverage_json = payload["coverage_json"]
                row.trade_metrics_json = payload["trade_metrics_json"]
                row.market_replay_json = payload["market_replay_json"]
                row.analytics_json = payload["analytics_json"]
                row.warnings_json = payload["warnings_json"]
                row.updated_at = now
            s.flush()
            return _quant_report_to_dict(row)
