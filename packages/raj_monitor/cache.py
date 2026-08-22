"""SQLite-backed local store — the agent's only persistence layer.

No Redis, no external service: a single SQLite file (WAL mode) that survives
process crashes and machine reboots. This module owns the connection lifecycle
and schema; :mod:`raj_monitor.queue` builds the durable queue on top of it.
"""

from __future__ import annotations

import sqlite3
import threading

from .exceptions import QueueError

_SCHEMA = """
CREATE TABLE IF NOT EXISTS queue (
    rowid       INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT    NOT NULL,
    payload     TEXT    NOT NULL,   -- JSON-encoded Envelope
    attempts    INTEGER NOT NULL DEFAULT 0,
    created_at  REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_queue_rowid ON queue(rowid);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


class Cache:
    """Thread-safe wrapper around a single SQLite database file."""

    def __init__(self, path: str) -> None:
        self.path = path
        self._lock = threading.RLock()
        try:
            # check_same_thread=False: we guard access with our own lock so the
            # connection can be shared by the uploader + ingest threads.
            self._conn = sqlite3.connect(path, check_same_thread=False, timeout=30)
            self._conn.row_factory = sqlite3.Row
            with self._lock:
                self._conn.execute("PRAGMA journal_mode=WAL;")
                self._conn.execute("PRAGMA synchronous=NORMAL;")
                self._conn.executescript(_SCHEMA)
                self._conn.commit()
        except sqlite3.Error as exc:
            raise QueueError(f"Cannot open cache database {path}: {exc}") from exc

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            try:
                cur = self._conn.execute(sql, params)
                self._conn.commit()
                return cur
            except sqlite3.Error as exc:
                raise QueueError(f"SQLite error: {exc}") from exc

    def executemany(self, sql: str, seq: list[tuple]) -> None:
        with self._lock:
            try:
                self._conn.executemany(sql, seq)
                self._conn.commit()
            except sqlite3.Error as exc:
                raise QueueError(f"SQLite error: {exc}") from exc

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            try:
                return list(self._conn.execute(sql, params).fetchall())
            except sqlite3.Error as exc:
                raise QueueError(f"SQLite error: {exc}") from exc

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        rows = self.query("SELECT value FROM meta WHERE key = ?", (key,))
        return rows[0]["value"] if rows else default

    def set_meta(self, key: str, value: str) -> None:
        self.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass
