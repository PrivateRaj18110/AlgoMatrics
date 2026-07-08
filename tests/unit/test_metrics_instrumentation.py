"""Unit tests for Phase 1 slice B instrumentation helpers."""

from __future__ import annotations

from algo_platform.shared.infrastructure.metrics_events import record_business_event
from algo_platform.shared.infrastructure.metrics_sampler import sample_db_pool, sample_once
from algo_platform.shared.infrastructure.prometheus import PrometheusMetrics


def _metrics() -> PrometheusMetrics:
    return PrometheusMetrics(namespace="algo", service="t", version="t", env="test")


def _sample(metrics: PrometheusMetrics, name: str, labels: dict[str, str]) -> float:
    value = metrics.registry.get_sample_value(name, labels)
    return value if value is not None else 0.0


def test_order_placed_increments_submitted() -> None:
    metrics = _metrics()
    record_business_event(
        metrics,
        "trading.order_placed.v1",
        {"broker": "paper", "side": "buy", "order_type": "market", "mode": "paper"},
    )
    assert (
        _sample(
            metrics,
            "algo_orders_submitted_total",
            {"broker": "paper", "side": "buy", "type": "market", "mode": "paper"},
        )
        == 1.0
    )


def test_order_filled_and_rejected_counters() -> None:
    metrics = _metrics()
    record_business_event(metrics, "trading.order_filled.v1", {"broker": "paper", "mode": "paper"})
    record_business_event(metrics, "trading.order_rejected.v1", {"mode": "paper"})
    record_business_event(metrics, "trading.order_cancelled.v1", {"mode": "live"})

    assert _sample(metrics, "algo_orders_filled_total", {"broker": "paper", "mode": "paper"}) == 1.0
    assert (
        _sample(
            metrics,
            "algo_orders_rejected_total",
            {"broker": "unknown", "mode": "paper", "reason": "rejected"},
        )
        == 1.0
    )
    assert (
        _sample(
            metrics,
            "algo_orders_rejected_total",
            {"broker": "unknown", "mode": "live", "reason": "cancelled"},
        )
        == 1.0
    )


def test_missing_payload_fields_default_to_unknown_without_error() -> None:
    metrics = _metrics()
    record_business_event(metrics, "trading.order_placed.v1", {})
    assert (
        _sample(
            metrics,
            "algo_orders_submitted_total",
            {"broker": "unknown", "side": "unknown", "type": "unknown", "mode": "unknown"},
        )
        == 1.0
    )


def test_unknown_event_type_is_ignored() -> None:
    metrics = _metrics()
    record_business_event(metrics, "identity.user_logged_in.v1", {})
    # No order counters should have been created with a value.
    assert _sample(metrics, "algo_orders_submitted_total", {}) == 0.0


class _FakePool:
    def size(self) -> int:
        return 10

    def checkedout(self) -> int:
        return 3

    def checkedin(self) -> int:
        return 7

    def overflow(self) -> int:
        return 0


class _FakeSyncEngine:
    pool = _FakePool()


class _FakeEngine:
    sync_engine = _FakeSyncEngine()


class _FakeRedis:
    def __init__(self, healthy: bool) -> None:
        self._healthy = healthy

    async def ping(self) -> bool:
        return self._healthy


def test_sample_db_pool_sets_all_states() -> None:
    metrics = _metrics()
    sample_db_pool(metrics, _FakeEngine())  # type: ignore[arg-type]
    assert _sample(metrics, "algo_db_pool_connections", {"state": "size"}) == 10.0
    assert _sample(metrics, "algo_db_pool_connections", {"state": "checked_out"}) == 3.0
    assert _sample(metrics, "algo_db_pool_connections", {"state": "checked_in"}) == 7.0


async def test_sample_once_sets_redis_up() -> None:
    metrics = _metrics()
    await sample_once(metrics, _FakeEngine(), _FakeRedis(True))  # type: ignore[arg-type]
    assert _sample(metrics, "algo_redis_up", {}) == 1.0
    await sample_once(metrics, _FakeEngine(), _FakeRedis(False))  # type: ignore[arg-type]
    assert _sample(metrics, "algo_redis_up", {}) == 0.0
