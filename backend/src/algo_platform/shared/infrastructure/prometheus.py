"""Prometheus instrumentation shared by every process.

This module owns the platform's Prometheus metric catalogue. It complements the
Redis day-bucket :class:`~algo_platform.shared.infrastructure.metrics.MetricsRecorder`
(which powers the admin business dashboard) by exposing high-resolution,
scrape-friendly time series for the Prometheus/Grafana pipeline.

Design constraints:

- One :class:`PrometheusMetrics` instance is created per process and stored on
  application/process state; it never connects to anything and is import-safe.
- Every collector lives on a private :class:`CollectorRegistry`, never the global
  default registry, so tests can build isolated instances without duplicate
  registration errors and so each process exposes only its own series.
- Labels are deliberately low cardinality. Route templates, broker slugs, and
  enum-like values only; never raw identifiers, symbols, or user input.
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
)
from prometheus_client import (
    ProcessCollector as _ProcessCollector,
)

__all__ = ["CONTENT_TYPE_LATEST", "PrometheusMetrics"]

# Latency buckets tuned for a web/trading API: sub-millisecond routing overhead
# is irrelevant, tail latency past ~10s means something is wrong.
_HTTP_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
# Broker/venue round trips are network bound and legitimately slower.
_BROKER_BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)
# Engine tick processing must stay tight; anything past a second is a red flag.
_TICK_BUCKETS = (0.001, 0.005, 0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)


class PrometheusMetrics:
    """Owns and exposes the process-local Prometheus metric catalogue."""

    def __init__(
        self,
        *,
        namespace: str = "algo",
        service: str,
        version: str,
        env: str,
        registry: CollectorRegistry | None = None,
    ) -> None:
        self.registry = registry or CollectorRegistry()
        self._namespace = namespace
        # Standard process metrics (CPU, memory, fds, uptime). No-op on
        # platforms without /proc, which keeps Windows dev environments happy.
        _ProcessCollector(registry=self.registry)

        self.app_info = Info(
            "app",
            "Static build information for this process.",
            namespace=namespace,
            registry=self.registry,
        )
        self.app_info.info({"service": service, "version": version, "env": env})

        # -- HTTP ------------------------------------------------------------
        self.http_requests_total = Counter(
            "http_requests_total",
            "Total HTTP requests handled by the API.",
            labelnames=("method", "route", "status"),
            namespace=namespace,
            registry=self.registry,
        )
        self.http_request_duration_seconds = Histogram(
            "http_request_duration_seconds",
            "HTTP request latency in seconds.",
            labelnames=("method", "route"),
            buckets=_HTTP_BUCKETS,
            namespace=namespace,
            registry=self.registry,
        )
        self.http_requests_in_progress = Gauge(
            "http_requests_in_progress",
            "In-flight HTTP requests.",
            labelnames=("method", "route"),
            namespace=namespace,
            registry=self.registry,
        )

        # -- Trading / business ---------------------------------------------
        self.orders_submitted_total = Counter(
            "orders_submitted_total",
            "Orders accepted for submission.",
            labelnames=("broker", "side", "type", "mode"),
            namespace=namespace,
            registry=self.registry,
        )
        self.orders_filled_total = Counter(
            "orders_filled_total",
            "Orders reported as filled.",
            labelnames=("broker", "mode"),
            namespace=namespace,
            registry=self.registry,
        )
        self.orders_rejected_total = Counter(
            "orders_rejected_total",
            "Orders rejected or cancelled before fill.",
            labelnames=("broker", "mode", "reason"),
            namespace=namespace,
            registry=self.registry,
        )
        self.positions_open = Gauge(
            "positions_open",
            "Currently open positions.",
            labelnames=("mode",),
            namespace=namespace,
            registry=self.registry,
        )
        self.pnl = Gauge(
            "pnl",
            "Aggregate profit and loss in base currency.",
            labelnames=("mode", "kind"),
            namespace=namespace,
            registry=self.registry,
        )
        self.strategy_runs_active = Gauge(
            "strategy_runs_active",
            "Active strategy runs owned by this process.",
            labelnames=("mode",),
            namespace=namespace,
            registry=self.registry,
        )

        # -- Broker adapters -------------------------------------------------
        self.broker_requests_total = Counter(
            "broker_requests_total",
            "Broker adapter calls by outcome.",
            labelnames=("broker", "operation", "outcome"),
            namespace=namespace,
            registry=self.registry,
        )
        self.broker_request_duration_seconds = Histogram(
            "broker_request_duration_seconds",
            "Broker adapter round-trip latency in seconds.",
            labelnames=("broker", "operation"),
            buckets=_BROKER_BUCKETS,
            namespace=namespace,
            registry=self.registry,
        )
        self.broker_up = Gauge(
            "broker_up",
            "Last observed broker connection health (1 healthy, 0 unhealthy).",
            labelnames=("broker",),
            namespace=namespace,
            registry=self.registry,
        )

        # -- Queues / streams / events --------------------------------------
        self.stream_depth = Gauge(
            "stream_depth",
            "Pending entries in a Redis stream / consumer group.",
            labelnames=("stream",),
            namespace=namespace,
            registry=self.registry,
        )
        self.events_published_total = Counter(
            "events_published_total",
            "Domain/engine events published to a stream.",
            labelnames=("stream",),
            namespace=namespace,
            registry=self.registry,
        )
        self.events_consumed_total = Counter(
            "events_consumed_total",
            "Stream entries consumed by outcome.",
            labelnames=("stream", "outcome"),
            namespace=namespace,
            registry=self.registry,
        )

        # -- Market data / engine -------------------------------------------
        self.market_ticks_total = Counter(
            "market_ticks_total",
            "Market data ticks processed.",
            labelnames=("source",),
            namespace=namespace,
            registry=self.registry,
        )
        self.engine_tick_duration_seconds = Histogram(
            "engine_tick_duration_seconds",
            "Trading-engine tick processing latency in seconds.",
            buckets=_TICK_BUCKETS,
            namespace=namespace,
            registry=self.registry,
        )

        # -- Infrastructure: database ---------------------------------------
        self.db_pool_connections = Gauge(
            "db_pool_connections",
            "SQLAlchemy engine pool connections by state.",
            labelnames=("state",),
            namespace=namespace,
            registry=self.registry,
        )

        # -- Infrastructure: redis ------------------------------------------
        self.redis_up = Gauge(
            "redis_up",
            "Last observed Redis health (1 healthy, 0 unhealthy).",
            namespace=namespace,
            registry=self.registry,
        )

        # -- WebSocket -------------------------------------------------------
        self.ws_connections = Gauge(
            "ws_connections",
            "Currently connected WebSocket clients.",
            namespace=namespace,
            registry=self.registry,
        )
        self.ws_messages_total = Counter(
            "ws_messages_total",
            "WebSocket frames by direction.",
            labelnames=("direction",),
            namespace=namespace,
            registry=self.registry,
        )

        # -- Frontend (RUM) --------------------------------------------------
        self.frontend_web_vitals = Histogram(
            "frontend_web_vitals",
            "Browser Web Vitals reported by the SPA, in milliseconds.",
            labelnames=("metric",),
            buckets=(50, 100, 250, 500, 1000, 2000, 4000, 8000),
            namespace=namespace,
            registry=self.registry,
        )
        self.frontend_errors_total = Counter(
            "frontend_errors_total",
            "Client-side errors reported by the SPA.",
            labelnames=("kind",),
            namespace=namespace,
            registry=self.registry,
        )

    def render(self) -> bytes:
        """Return the current metrics in Prometheus text exposition format."""
        return generate_latest(self.registry)
