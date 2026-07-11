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
from typing import Any, Iterator, Optional

from sqlalchemy import Table, select
from sqlalchemy.orm import Session

from app.database.session import database_enabled, get_sessionmaker
from app.models import Event, IngestDedup, Log, Machine, Metric, Trade, utcnow

# Read caps mirror the old in-memory bounds so router `[:limit]` slicing is
# identical and we never scan an unbounded table for a feed.
EVENTS_CAP = 400
LOGS_CAP = 1000
TRADES_CAP = 1000

# A live host flips to "offline" on the dashboard after this much heartbeat
# silence (matches realtime.publisher._LIVE_STALE_AFTER_SEC).
STALE_AFTER_SEC = 20.0


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


def _iso(dt: datetime | None) -> str:
    return _aware(dt).isoformat() if dt is not None else ""


def _parse_iso(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return utcnow()


def _machine_to_dict(m: Machine, now: datetime) -> dict[str, Any]:
    status, py_status = m.status, m.python_status
    # Derive-on-read staleness for live hosts (keeps the publisher unchanged).
    if m.live and m.last_heartbeat is not None:
        if (now - _aware(m.last_heartbeat)).total_seconds() > STALE_AFTER_SEC:
            status, py_status = "offline", "offline"
    return {
        "id": m.id, "name": m.name, "location": m.location, "provider": m.provider,
        "status": status, "cpu": m.cpu, "ram": m.ram, "disk": m.disk,
        "temperatureC": m.temperature_c, "internetMs": m.internet_ms,
        "brokerPingMs": m.broker_ping_ms, "pythonStatus": py_status,
        "uptimeSec": m.uptime_sec, "lastHeartbeat": _iso(m.last_heartbeat),
        "strategyCount": m.strategy_count,
    }


def _event_to_dict(e: Event) -> dict[str, Any]:
    return {"id": e.id, "time": _iso(e.time), "category": e.category,
            "severity": e.severity, "source": e.source, "message": e.message}


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
}


def _to_machine_columns(d: dict[str, Any]) -> dict[str, Any]:
    cols: dict[str, Any] = {}
    for key, col in _MACHINE_KEY_MAP.items():
        if key not in d:
            continue
        cols[col] = _parse_iso(d[key]) if col == "last_heartbeat" else d[key]
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
        with _read_session() as s:
            rows = s.execute(
                select(Event).order_by(Event.time.desc(), Event.id.desc()).limit(EVENTS_CAP)
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
