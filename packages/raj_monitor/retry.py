"""Retry with exponential backoff + a simple circuit breaker.

Two reusable primitives:

* :func:`backoff_delays` — a generator of capped, jittered delays.
* :class:`CircuitBreaker` — trips open after N consecutive failures and refuses
  calls for a cooldown window, so a dead backend doesn't get hammered.

Both are thread-safe enough for the agent's single uploader thread.
"""

from __future__ import annotations

import random
import threading
import time
from collections.abc import Iterator

from . import constants
from .exceptions import CircuitOpenError


def backoff_delays(
    count: int = constants.DEFAULT_RETRY_COUNT,
    base: float = constants.DEFAULT_BACKOFF_BASE,
    cap: float = constants.DEFAULT_BACKOFF_MAX,
) -> Iterator[float]:
    """Yield ``count`` delays: base*2**n capped at ``cap`` with +-25% jitter."""
    for n in range(count):
        raw = min(cap, base * (2 ** n))
        jitter = raw * 0.25
        yield max(0.0, raw + random.uniform(-jitter, jitter))


class CircuitBreaker:
    """Trip open after consecutive failures; auto half-open after cooldown."""

    def __init__(
        self,
        threshold: int = constants.DEFAULT_BREAKER_THRESHOLD,
        cooldown: float = constants.DEFAULT_BREAKER_COOLDOWN,
    ) -> None:
        self._threshold = max(1, threshold)
        self._cooldown = cooldown
        self._failures = 0
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    @property
    def is_open(self) -> bool:
        with self._lock:
            return self._is_open_locked()

    def _is_open_locked(self) -> bool:
        if self._opened_at is None:
            return False
        if time.time() - self._opened_at >= self._cooldown:
            # Cooldown elapsed -> half-open: allow the next attempt through.
            return False
        return True

    def before_request(self) -> None:
        """Raise :class:`CircuitOpenError` if the breaker is currently open."""
        if self.is_open:
            raise CircuitOpenError("Circuit breaker is open; backend unavailable")

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self._threshold and self._opened_at is None:
                self._opened_at = time.time()
            elif self._opened_at is not None:
                # Failed during half-open probe -> restart the cooldown.
                self._opened_at = time.time()

    def state(self) -> str:
        with self._lock:
            if self._opened_at is None:
                return "closed"
            return "open" if self._is_open_locked() else "half-open"
