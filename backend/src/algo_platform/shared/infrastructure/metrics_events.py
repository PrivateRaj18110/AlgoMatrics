"""Derive Prometheus business metrics from relayed domain events.

The outbox worker relays every business event, which makes it the single, clean
place to translate domain events into trading metrics without threading a
metrics dependency through every domain service. This module is pure and
side-effecting only on the passed-in :class:`PrometheusMetrics`, so it is unit
testable in isolation.
"""

from __future__ import annotations

from typing import Any

from algo_platform.shared.infrastructure.prometheus import PrometheusMetrics

_UNKNOWN = "unknown"

# Order lifecycle event types that map to a rejection-style counter.
_REJECTION_EVENTS = frozenset(
    {"trading.order_rejected.v1", "trading.order_cancelled.v1"}
)


def _label(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return _UNKNOWN


def record_business_event(
    metrics: PrometheusMetrics, event_type: str, payload: dict[str, Any]
) -> None:
    """Increment trading counters for a known business event type.

    Unknown event types are ignored; label values fall back to ``unknown`` so a
    missing payload field can never raise inside the relay hot path.
    """
    broker = _label(payload, "broker", "broker_slug")
    mode = _label(payload, "mode")

    if event_type == "trading.order_placed.v1":
        metrics.orders_submitted_total.labels(
            broker=broker,
            side=_label(payload, "side"),
            type=_label(payload, "order_type", "type"),
            mode=mode,
        ).inc()
    elif event_type == "trading.order_filled.v1":
        metrics.orders_filled_total.labels(broker=broker, mode=mode).inc()
    elif event_type in _REJECTION_EVENTS:
        reason = "cancelled" if event_type.endswith("cancelled.v1") else "rejected"
        metrics.orders_rejected_total.labels(
            broker=broker, mode=mode, reason=reason
        ).inc()
