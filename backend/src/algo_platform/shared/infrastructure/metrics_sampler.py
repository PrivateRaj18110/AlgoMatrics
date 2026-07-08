"""Periodic sampler for infrastructure gauges that have no natural event hook.

Connection-pool utilisation and Redis reachability are level metrics rather than
counters, so a lightweight background task samples them on an interval and
updates the Prometheus gauges. Runs inside the API process lifespan.
"""

from __future__ import annotations

import asyncio
import contextlib

import structlog
from sqlalchemy.ext.asyncio import AsyncEngine

from algo_platform.shared.infrastructure.prometheus import PrometheusMetrics
from algo_platform.shared.infrastructure.redis_gateway import RedisGateway

logger = structlog.get_logger("metrics")

_POOL_STATES = ("size", "checked_out", "checked_in", "overflow")


def sample_db_pool(metrics: PrometheusMetrics, engine: AsyncEngine) -> None:
    """Update database pool gauges. Best effort across pool implementations."""
    pool = engine.sync_engine.pool
    readers = {
        "size": getattr(pool, "size", None),
        "checked_out": getattr(pool, "checkedout", None),
        "checked_in": getattr(pool, "checkedin", None),
        "overflow": getattr(pool, "overflow", None),
    }
    for state in _POOL_STATES:
        reader = readers[state]
        if reader is None:
            continue
        try:
            metrics.db_pool_connections.labels(state=state).set(float(reader()))
        except Exception:  # noqa: S112 - pool introspection is diagnostic only
            # Never let a pool-stats read disturb the application.
            continue


async def sample_once(
    metrics: PrometheusMetrics, engine: AsyncEngine, redis: RedisGateway
) -> None:
    sample_db_pool(metrics, engine)
    try:
        healthy = await redis.ping()
    except Exception:
        healthy = False
    metrics.redis_up.set(1.0 if healthy else 0.0)


async def run_infra_sampler(
    metrics: PrometheusMetrics,
    engine: AsyncEngine,
    redis: RedisGateway,
    *,
    interval_seconds: float,
    stop: asyncio.Event,
) -> None:
    logger.info("metrics.infra_sampler_started", interval=interval_seconds)
    while not stop.is_set():
        try:
            await sample_once(metrics, engine, redis)
        except Exception:
            logger.warning("metrics.infra_sample_failed")
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
