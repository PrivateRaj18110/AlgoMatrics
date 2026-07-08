"""Event handlers for the domain worker roles.

Handlers are small and dependency-light: they receive the shared
:class:`WorkerContext` and an event envelope. The heavier domain logic largely
runs synchronously in the request/engine paths; these async workers add
per-domain processing seams (analytics aggregation, notification fan-out, and
per-domain observability) that scale independently of the request path.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

import structlog

from algo_platform.processes.workers.base import WorkerContext
from algo_platform.shared.domain.types import utc_now

EventHandler = Callable[[WorkerContext, dict[str, Any]], Awaitable[None]]

logger = structlog.get_logger("worker.handlers")

_ANALYTICS_RETENTION_SECONDS = 60 * 60 * 24 * 90

# event_type -> (title, severity) for events worth notifying an organization about.
_NOTIFY_MAP: dict[str, tuple[str, str]] = {
    "trading.order_rejected.v1": ("Order rejected", "warning"),
    "risk.limit_triggered.v1": ("Risk limit triggered", "critical"),
    "risk.kill_switch_activated.v1": ("Kill switch activated", "critical"),
    "billing.subscription_changed.v1": ("Subscription updated", "info"),
    "billing.payment_succeeded.v1": ("Payment received", "info"),
    "billing.payment_failed.v1": ("Payment failed", "warning"),
}


async def analytics_handler(ctx: WorkerContext, event: dict[str, Any]) -> None:
    """Aggregate event volume into per-day Redis counters keyed by event type."""
    event_type = str(event.get("event_type", "unknown"))
    key = f"analytics:events:{utc_now():%Y%m%d}"
    await ctx.redis.hincrby(key, event_type, 1)
    await ctx.redis.expire(key, _ANALYTICS_RETENTION_SECONDS)


async def notification_handler(ctx: WorkerContext, event: dict[str, Any]) -> None:
    """Create an organization notification for significant business events."""
    event_type = str(event.get("event_type", ""))
    mapping = _NOTIFY_MAP.get(event_type)
    org_raw = event.get("organization_id")
    if mapping is None or not org_raw:
        return
    title, severity = mapping
    # Imported lazily to keep this module import-light and avoid a hard coupling.
    from algo_platform.modules.notifications.application.service import NotificationService

    async with ctx.session_factory() as session:
        await NotificationService(session, ctx.redis).notify(
            organization_id=UUID(str(org_raw)),
            title=title,
            type_=event_type.split(".")[0],
            severity=severity,  # type: ignore[arg-type]
            payload={"event_type": event_type, "event_id": event.get("event_id")},
        )
        await session.commit()


def observability_handler(domain: str) -> EventHandler:
    """Build a handler that records a per-domain processing seam (log + metric).

    Used by domain workers whose core mutations already happen synchronously;
    this gives each domain an independent, observable async consumer to extend.
    """

    async def handle(ctx: WorkerContext, event: dict[str, Any]) -> None:
        logger.info(
            "worker.domain_event",
            domain=domain,
            event_type=event.get("event_type"),
            event_id=event.get("event_id"),
            organization_id=event.get("organization_id"),
        )

    return handle
