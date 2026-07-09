"""Unit tests for the circuit breaker + readiness aggregation (Phase 18)."""

from __future__ import annotations

import pytest

from algo_platform.modules.notifications.infrastructure.channels import (
    OutboundNotification,
    WebhookNotificationChannel,
)
from algo_platform.shared.application.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)
from algo_platform.shared.application.readiness import ProbeResult, is_ready, overall_status


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _breaker(clock: FakeClock, **kw: object) -> CircuitBreaker:
    params: dict[str, object] = {
        "failure_threshold": 3,
        "reset_timeout": 30.0,
        "half_open_max_calls": 1,
        "clock": clock,
    }
    params.update(kw)
    return CircuitBreaker(**params)  # type: ignore[arg-type]


# -- circuit breaker --------------------------------------------------------


def test_starts_closed_and_allows() -> None:
    cb = _breaker(FakeClock())
    assert cb.state is CircuitState.CLOSED
    assert cb.allow_request() is True


def test_trips_open_after_threshold_failures() -> None:
    cb = _breaker(FakeClock())
    for _ in range(3):
        cb.record_failure()
    assert cb.state is CircuitState.OPEN
    assert cb.allow_request() is False


def test_success_resets_failure_count() -> None:
    cb = _breaker(FakeClock())
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    cb.record_failure()
    assert cb.state is CircuitState.CLOSED


def test_transitions_to_half_open_after_cooldown() -> None:
    clock = FakeClock()
    cb = _breaker(clock)
    for _ in range(3):
        cb.record_failure()
    assert cb.state is CircuitState.OPEN
    clock.advance(29)
    assert cb.state is CircuitState.OPEN
    clock.advance(2)  # total 31 >= 30
    assert cb.state is CircuitState.HALF_OPEN


def test_half_open_limits_trial_calls() -> None:
    clock = FakeClock()
    cb = _breaker(clock, half_open_max_calls=1)
    for _ in range(3):
        cb.record_failure()
    clock.advance(31)
    assert cb.allow_request() is True  # first trial permitted
    assert cb.allow_request() is False  # second blocked while half-open


def test_half_open_success_closes() -> None:
    clock = FakeClock()
    cb = _breaker(clock)
    for _ in range(3):
        cb.record_failure()
    clock.advance(31)
    cb.allow_request()
    cb.record_success()
    assert cb.state is CircuitState.CLOSED


def test_half_open_failure_reopens() -> None:
    clock = FakeClock()
    cb = _breaker(clock)
    for _ in range(3):
        cb.record_failure()
    clock.advance(31)
    cb.allow_request()
    cb.record_failure()
    assert cb.state is CircuitState.OPEN


def test_invalid_config_rejected() -> None:
    with pytest.raises(ValueError):
        CircuitBreaker(failure_threshold=0)
    with pytest.raises(ValueError):
        CircuitBreaker(half_open_max_calls=0)


async def test_call_passes_through_and_records_success() -> None:
    cb = _breaker(FakeClock())

    async def ok() -> int:
        return 42

    assert await cb.call(ok) == 42
    assert cb.state is CircuitState.CLOSED


async def test_call_records_failure_and_reraises() -> None:
    cb = _breaker(FakeClock(), failure_threshold=1)

    async def boom() -> int:
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        await cb.call(boom)
    assert cb.state is CircuitState.OPEN


async def test_call_short_circuits_when_open() -> None:
    clock = FakeClock()
    cb = _breaker(clock, failure_threshold=1)

    async def boom() -> int:
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        await cb.call(boom)

    calls = 0

    async def counted() -> int:
        nonlocal calls
        calls += 1
        return 1

    with pytest.raises(CircuitOpenError):
        await cb.call(counted)
    assert calls == 0  # never invoked while open


# -- readiness aggregation --------------------------------------------------


def test_overall_status_ok_when_all_critical_healthy() -> None:
    results = [ProbeResult("postgres", True), ProbeResult("redis", True)]
    assert overall_status(results) == "ok"
    assert is_ready(results) is True


def test_degraded_when_a_critical_probe_fails() -> None:
    results = [ProbeResult("postgres", False), ProbeResult("redis", True)]
    assert overall_status(results) == "degraded"
    assert is_ready(results) is False


def test_non_critical_failure_does_not_degrade() -> None:
    results = [
        ProbeResult("postgres", True),
        ProbeResult("push", False, critical=False),
    ]
    assert overall_status(results) == "ok"


# -- webhook channel + breaker integration ----------------------------------


class FlakyClient:
    def __init__(self) -> None:
        self.calls = 0

    async def post(self, *args: object, **kwargs: object) -> None:
        self.calls += 1
        raise RuntimeError("endpoint down")


async def test_webhook_breaker_opens_and_short_circuits() -> None:
    client = FlakyClient()
    breaker = CircuitBreaker(name="wh", failure_threshold=1)
    channel = WebhookNotificationChannel(client, breaker=breaker)  # type: ignore[arg-type]
    note = OutboundNotification(type="t", severity="warning", title="x", body="y", payload={})

    # First send fails and trips the breaker (threshold 1).
    with pytest.raises(RuntimeError):
        await channel.send(note, target="https://example.com/hook")
    assert breaker.state is CircuitState.OPEN

    # Second send is rejected fast without hitting the endpoint again.
    with pytest.raises(CircuitOpenError):
        await channel.send(note, target="https://example.com/hook")
    assert client.calls == 1
