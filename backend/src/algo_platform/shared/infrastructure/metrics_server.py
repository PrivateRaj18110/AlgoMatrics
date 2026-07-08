"""Prometheus exposition server for non-HTTP background processes.

The API exposes /metrics through FastAPI. Background processes (worker,
trading-engine, market-data, scheduler) have no HTTP surface, so they start a
tiny dedicated Prometheus server on ``METRICS_PORT`` (default 9100) that serves
only their own registry.
"""

from __future__ import annotations

import structlog
from prometheus_client import start_http_server

from algo_platform.config import Settings
from algo_platform.shared.infrastructure.prometheus import PrometheusMetrics

logger = structlog.get_logger("metrics")

_PROCESS_VERSION = "0.1.0"


def start_process_metrics(settings: Settings, service: str) -> PrometheusMetrics | None:
    """Build the process metric catalogue and start its scrape server.

    Returns ``None`` (and starts nothing) when metrics are disabled so callers
    can guard instrumentation on a single truthiness check.
    """
    if not settings.metrics_enabled:
        return None
    metrics = PrometheusMetrics(
        namespace=settings.metrics_namespace,
        service=service,
        version=_PROCESS_VERSION,
        env=settings.app_env,
    )
    try:
        start_http_server(settings.metrics_port, registry=metrics.registry)
        logger.info("metrics.server_started", service=service, port=settings.metrics_port)
    except OSError:
        # A bound port must never take down a trading process; degrade to no
        # scraping rather than crash.
        logger.warning("metrics.server_bind_failed", service=service, port=settings.metrics_port)
    return metrics
