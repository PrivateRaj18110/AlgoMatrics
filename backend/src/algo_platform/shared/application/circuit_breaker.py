"""A reusable circuit breaker for guarding flaky external dependencies.

The state machine is pure and clock-injectable so it is fully unit testable; the
async ``call`` helper wraps a coroutine and short-circuits with
``CircuitOpenError`` while the breaker is open, preventing a failing dependency
from exhausting workers with doomed calls.

States:
- **closed**   — calls flow; consecutive failures are counted.
- **open**     — calls are rejected fast until ``reset_timeout`` elapses.
- **half_open** — a limited number of trial calls probe recovery; a success
  closes the breaker, a failure re-opens it.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import TypeVar

T = TypeVar("T")


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when a call is rejected because the breaker is open."""

    def __init__(self, name: str) -> None:
        super().__init__(f"circuit '{name}' is open")
        self.name = name


class CircuitBreaker:
    def __init__(
        self,
        *,
        name: str = "default",
        failure_threshold: int = 5,
        reset_timeout: float = 30.0,
        half_open_max_calls: int = 1,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if half_open_max_calls < 1:
            raise ValueError("half_open_max_calls must be >= 1")
        self._name = name
        self._failure_threshold = failure_threshold
        self._reset_timeout = reset_timeout
        self._half_open_max_calls = half_open_max_calls
        self._clock = clock
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._half_open_calls = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> CircuitState:
        # Lazily transition open -> half_open once the cooldown has elapsed.
        if self._state is CircuitState.OPEN and self._cooldown_elapsed():
            self._state = CircuitState.HALF_OPEN
            self._half_open_calls = 0
        return self._state

    def _cooldown_elapsed(self) -> bool:
        return (self._clock() - self._opened_at) >= self._reset_timeout

    def allow_request(self) -> bool:
        """Whether a call may proceed right now (advances state as needed)."""

        state = self.state
        if state is CircuitState.CLOSED:
            return True
        if state is CircuitState.HALF_OPEN:
            if self._half_open_calls < self._half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False
        return False

    def record_success(self) -> None:
        self._failures = 0
        self._half_open_calls = 0
        self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        if self.state is CircuitState.HALF_OPEN:
            self._trip()
            return
        self._failures += 1
        if self._failures >= self._failure_threshold:
            self._trip()

    def _trip(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = self._clock()
        self._half_open_calls = 0

    async def call(self, func: Callable[[], Awaitable[T]]) -> T:
        """Run ``func`` under the breaker; raise ``CircuitOpenError`` if open."""

        if not self.allow_request():
            raise CircuitOpenError(self._name)
        try:
            result = await func()
        except Exception:
            self.record_failure()
            raise
        self.record_success()
        return result
