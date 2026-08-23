"""Shared sqlite ops-schema helper for operations read-layer tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, text

SCHEMA = """
CREATE TABLE machines (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    location TEXT DEFAULT '',
    provider TEXT DEFAULT '',
    status TEXT DEFAULT 'online',
    cpu REAL DEFAULT 0,
    ram REAL DEFAULT 0,
    disk REAL DEFAULT 0,
    temperature_c REAL,
    internet_ms REAL DEFAULT 0,
    broker_ping_ms REAL DEFAULT 0,
    python_status TEXT DEFAULT 'online',
    uptime_sec INTEGER DEFAULT 0,
    last_heartbeat TIMESTAMP,
    strategy_count INTEGER DEFAULT 0,
    live INTEGER DEFAULT 1,
    agent_id TEXT,
    agent_version TEXT,
    hostname TEXT DEFAULT '',
    environment TEXT DEFAULT '',
    last_event TIMESTAMP,
    last_trade TIMESTAMP,
    last_error TIMESTAMP,
    last_successful_upload TIMESTAMP,
    queue_depth INTEGER,
    oldest_pending_age_sec INTEGER,
    transport_state TEXT,
    current_session_id TEXT,
    trading_process_state TEXT,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
CREATE TABLE events (
    id TEXT PRIMARY KEY,
    envelope_id TEXT UNIQUE,
    time TIMESTAMP NOT NULL,
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    source TEXT NOT NULL,
    message TEXT NOT NULL,
    machine_id TEXT,
    event_type TEXT,
    strategy TEXT,
    symbol TEXT,
    session_id TEXT,
    sequence_id INTEGER,
    payload_summary TEXT,
    created_at TIMESTAMP NOT NULL
);
CREATE TABLE trades (
    id TEXT PRIMARY KEY,
    envelope_id TEXT UNIQUE,
    time TIMESTAMP NOT NULL,
    strategy TEXT DEFAULT '',
    machine TEXT DEFAULT '',
    machine_id TEXT,
    broker TEXT DEFAULT '',
    account TEXT DEFAULT '',
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    action TEXT,
    entry REAL DEFAULT 0,
    exit REAL,
    quantity REAL DEFAULT 0,
    pnl REAL DEFAULT 0,
    latency_ms REAL DEFAULT 0,
    duration_sec INTEGER DEFAULT 0,
    status TEXT DEFAULT 'closed',
    created_at TIMESTAMP NOT NULL
);
CREATE TABLE logs (
    id TEXT PRIMARY KEY,
    time TIMESTAMP NOT NULL,
    source TEXT,
    level TEXT,
    logger TEXT,
    message TEXT
);
"""


def sqlite_url(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{path.as_posix()}"
    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        for statement in SCHEMA.split(";"):
            stmt = statement.strip()
            if stmt:
                conn.execute(text(stmt))
    engine.dispose()
    return url


@contextmanager
def ops_sqlite_db(filename: str) -> Iterator[str]:
    """Workspace-local sqlite file. Avoids Windows pytest-of-Light tmp_path ACLs."""

    path = Path(__file__).resolve().parents[2] / ".pytest_sqlite" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    url = sqlite_url(path)
    try:
        yield url
    finally:
        with suppress(PermissionError):
            path.unlink(missing_ok=True)


def insert_mixed_batch(url: str, *, duplicate: bool = False) -> None:
    """Persist the f9bee1a mixed batch as the ingest layer would after classification."""

    now = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT OR IGNORE INTO machines (
                    id, name, status, live, hostname, last_heartbeat,
                    last_successful_upload, queue_depth, created_at, updated_at
                ) VALUES (
                    :id, :name, 'online', 1, :name, :hb, :hb, 0, :hb, :hb
                )
                """
            ),
            {"id": "mch-gcp-1", "name": "gcp-trading-1", "hb": now},
        )
        events = [
            ("evt-hb", "env-hb", "heartbeat", None, None, "heartbeat ok"),
            ("evt-ss", "env-ss", "strategy_status", "Alpha", "NIFTY", "running"),
            ("evt-sys", "env-sys", "system_status", None, None, "api_call"),
            ("evt-ord", "env-ord", "order", "Alpha", "NIFTY", "limit buy"),
            ("evt-tc", "env-tc", "trade_closed", "Alpha", "NIFTY", "closed"),
        ]
        for eid, envelope, kind, strategy, symbol, message in events:
            conn.execute(
                text(
                    """
                    INSERT OR IGNORE INTO events (
                        id, envelope_id, time, category, severity, source, message,
                        machine_id, event_type, strategy, symbol, created_at
                    ) VALUES (
                        :id, :envelope, :time, 'telemetry', 'info', 'agent', :message,
                        'mch-gcp-1', :kind, :strategy, :symbol, :time
                    )
                    """
                ),
                {
                    "id": eid,
                    "envelope": envelope,
                    "time": now,
                    "message": message,
                    "kind": kind,
                    "strategy": strategy,
                    "symbol": symbol,
                },
            )
        conn.execute(
            text(
                """
                INSERT OR IGNORE INTO trades (
                    id, envelope_id, time, strategy, machine, machine_id, symbol,
                    direction, entry, exit, quantity, pnl, latency_ms, duration_sec,
                    status, created_at
                ) VALUES (
                    'trd-1', 'env-tc', :time, 'Alpha', 'gcp-trading-1', 'mch-gcp-1',
                    'NIFTY', 'long', 100.5, 101.5, 1, 12.5, 8, 30, 'closed', :time
                )
                """
            ),
            {"time": now},
        )
        if duplicate:
            conn.execute(
                text(
                    """
                    INSERT OR IGNORE INTO trades (
                        id, envelope_id, time, strategy, machine, machine_id, symbol,
                        direction, entry, exit, quantity, pnl, latency_ms, duration_sec,
                        status, created_at
                    ) VALUES (
                        'trd-dup', 'env-tc', :time, 'Alpha', 'gcp-trading-1', 'mch-gcp-1',
                        'NIFTY', 'long', 100.5, 101.5, 1, 12.5, 8, 30, 'closed', :time
                    )
                    """
                ),
                {"time": now + timedelta(seconds=1)},
            )
    engine.dispose()


def insert_demo_seed_data(url: str) -> None:
    """Insert legacy demo/seed rows that must be filtered from the production read path."""

    now = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
    engine = create_engine(url, future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT OR IGNORE INTO machines (
                    id, name, location, provider, status, live, hostname, last_heartbeat,
                    last_successful_upload, queue_depth, created_at, updated_at
                ) VALUES (
                    'mch-london', 'London VPS', 'London', 'Beeks', 'online', 0, 'london-host', :hb, :hb, 0, :hb, :hb
                )
                """
            ),
            {"hb": now},
        )
        conn.execute(
            text(
                """
                INSERT OR IGNORE INTO machines (
                    id, name, location, provider, status, live, hostname, last_heartbeat,
                    last_successful_upload, queue_depth, created_at, updated_at
                ) VALUES (
                    'mch-pc', 'Personal Computer', 'Mumbai', 'Local', 'offline', 0, 'pc-host', :hb, :hb, 0, :hb, :hb
                )
                """
            ),
            {"hb": now},
        )
        conn.execute(
            text(
                """
                INSERT OR IGNORE INTO trades (
                    id, envelope_id, time, strategy, machine, machine_id, broker, account, symbol,
                    direction, entry, exit, quantity, pnl, latency_ms, duration_sec,
                    status, created_at
                ) VALUES (
                    'trd-demo-1', NULL, :time, 'Mean Reversion FX', 'London VPS', 'mch-london',
                    'IC Markets', 'LIVE-001', 'EURUSD', 'long', 1.08, 1.09, 1, 100.0, 5, 60, 'closed', :time
                )
                """
            ),
            {"time": now},
        )
        conn.execute(
            text(
                """
                INSERT OR IGNORE INTO trades (
                    id, envelope_id, time, strategy, machine, machine_id, broker, account, symbol,
                    direction, entry, exit, quantity, pnl, latency_ms, duration_sec,
                    status, created_at
                ) VALUES (
                    'trd-demo-2', NULL, :time, 'Gold Scalper', 'London VPS', 'mch-london',
                    'Pepperstone', 'LIVE-002', 'XAUUSD', 'short', 2350, 2340, 1, 250.0, 4, 45, 'closed', :time
                )
                """
            ),
            {"time": now},
        )
        conn.execute(
            text(
                """
                INSERT OR IGNORE INTO events (
                    id, envelope_id, time, category, severity, source, message,
                    machine_id, event_type, strategy, symbol, created_at
                ) VALUES (
                    'evt-demo-1', NULL, :time, 'strategy', 'info', 'London VPS', 'Strategy started',
                    'mch-london', 'strategy_status', 'Mean Reversion FX', 'EURUSD', :time
                )
                """
            ),
            {"time": now},
        )
        conn.execute(
            text(
                """
                INSERT OR IGNORE INTO logs (
                    id, time, source, level, logger, message
                ) VALUES (
                    'log-demo-1', :time, 'host.london', 'info', 'MR-FX', 'Demo log message'
                )
                """
            ),
            {"time": now},
        )
    engine.dispose()

