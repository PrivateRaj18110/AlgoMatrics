"""Persistent, crash-safe queue for outbound telemetry.

Backed by SQLite (:mod:`raj_monitor.cache`), so queued events survive process
crashes *and* machine reboots — the core "never lose events" guarantee. The
uploader pops a batch, ships it, and only deletes rows on success; a crash
mid-upload simply re-sends (the backend ingest is idempotent enough for
monitoring purposes).

Overflow policy: when the queue exceeds ``max_size`` the **oldest** rows are
dropped so the newest telemetry is always retained.
"""

from __future__ import annotations

import json
import threading

from .cache import Cache
from .types import Envelope, QueuedItem


class PersistentQueue:
    """A durable FIFO of :class:`Envelope` items."""

    def __init__(self, cache: Cache, max_size: int) -> None:
        self._cache = cache
        self._max_size = max(1, max_size)
        self._lock = threading.Lock()
        self.dropped_total = 0

    # -- writes ------------------------------------------------------------
    def put(self, env: Envelope) -> None:
        """Append an envelope, enforcing the size cap (drop-oldest)."""
        with self._lock:
            self._cache.execute(
                "INSERT INTO queue(kind, payload, attempts, created_at) VALUES(?,?,?,?)",
                (env.kind, json.dumps(env.as_dict(), default=str), 0, _now()),
            )
            self._enforce_cap_locked()

    def put_many(self, envelopes: list[Envelope]) -> None:
        if not envelopes:
            return
        with self._lock:
            self._cache.executemany(
                "INSERT INTO queue(kind, payload, attempts, created_at) VALUES(?,?,?,?)",
                [(e.kind, json.dumps(e.as_dict(), default=str), 0, _now()) for e in envelopes],
            )
            self._enforce_cap_locked()

    # -- reads -------------------------------------------------------------
    def peek_batch(self, limit: int) -> list[QueuedItem]:
        """Return up to ``limit`` oldest items without removing them."""
        rows = self._cache.query(
            "SELECT rowid, payload, attempts, created_at FROM queue "
            "ORDER BY rowid ASC LIMIT ?",
            (int(limit),),
        )
        items: list[QueuedItem] = []
        for r in rows:
            try:
                env = Envelope.from_dict(json.loads(r["payload"]))
            except (ValueError, KeyError):
                # Corrupt row: drop it so it can't wedge the queue forever.
                self.delete([r["rowid"]])
                continue
            items.append(QueuedItem(rowid=r["rowid"], envelope=env,
                                    attempts=r["attempts"], created_at=r["created_at"]))
        return items

    def delete(self, rowids: list[int]) -> None:
        """Remove successfully-uploaded rows."""
        if not rowids:
            return
        placeholders = ",".join("?" for _ in rowids)
        self._cache.execute(
            f"DELETE FROM queue WHERE rowid IN ({placeholders})", tuple(rowids)
        )

    def mark_attempt(self, rowids: list[int]) -> None:
        """Increment the retry counter for items that failed to upload."""
        if not rowids:
            return
        placeholders = ",".join("?" for _ in rowids)
        self._cache.execute(
            f"UPDATE queue SET attempts = attempts + 1 WHERE rowid IN ({placeholders})",
            tuple(rowids),
        )

    # -- introspection -----------------------------------------------------
    def size(self) -> int:
        rows = self._cache.query("SELECT COUNT(*) AS n FROM queue")
        return rows[0]["n"] if rows else 0

    def _enforce_cap_locked(self) -> None:
        n = self.size()
        if n <= self._max_size:
            return
        overflow = n - self._max_size
        self._cache.execute(
            "DELETE FROM queue WHERE rowid IN "
            "(SELECT rowid FROM queue ORDER BY rowid ASC LIMIT ?)",
            (overflow,),
        )
        self.dropped_total += overflow


def _now() -> float:
    import time
    return time.time()
