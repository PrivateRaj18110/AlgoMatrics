"""Registry of worker roles and selection from configuration."""

from __future__ import annotations

from collections.abc import Callable

import structlog

from algo_platform.processes.workers.base import WorkerContext, WorkerRole
from algo_platform.processes.workers.consumer_worker import EventConsumerWorker
from algo_platform.processes.workers.email import EmailWorker
from algo_platform.processes.workers.handlers import (
    analytics_handler,
    notification_handler,
    observability_handler,
)
from algo_platform.processes.workers.relay import OutboxRelayWorker

logger = structlog.get_logger("worker.registry")

WorkerFactory = Callable[[WorkerContext], WorkerRole]


def _consumer(
    name: str, *, handler: object, prefixes: tuple[str, ...] | None
) -> WorkerFactory:
    def factory(ctx: WorkerContext) -> WorkerRole:
        return EventConsumerWorker(
            ctx,
            name=name,
            group=f"worker:{name}",
            handler=handler,  # type: ignore[arg-type]
            event_prefixes=prefixes,
        )

    return factory


# Name -> factory. Relay/email are outbox pollers; the rest consume the events
# stream, each with its own consumer group so they scale independently.
REGISTRY: dict[str, WorkerFactory] = {
    OutboxRelayWorker.name: OutboxRelayWorker,
    EmailWorker.name: EmailWorker,
    "notification": _consumer(
        "notification",
        handler=notification_handler,
        prefixes=("trading.order", "risk.", "billing."),
    ),
    "analytics": _consumer("analytics", handler=analytics_handler, prefixes=None),
    "audit": _consumer(
        "audit",
        handler=observability_handler("audit"),
        prefixes=("auth.", "identity.", "admin."),
    ),
    "report": _consumer(
        "report", handler=observability_handler("report"), prefixes=("trading.", "billing.")
    ),
    "billing": _consumer(
        "billing", handler=observability_handler("billing"), prefixes=("billing.",)
    ),
    "settlement": _consumer(
        "settlement",
        handler=observability_handler("settlement"),
        prefixes=("billing.payment", "settlement."),
    ),
    "trading": _consumer(
        "trading", handler=observability_handler("trading"), prefixes=("trading.",)
    ),
}


def available_roles() -> list[str]:
    return sorted(REGISTRY)


def build_roles(names: list[str], ctx: WorkerContext) -> list[WorkerRole]:
    """Instantiate the selected roles. ``["all"]`` (or empty) selects every role."""
    selected = available_roles() if (not names or "all" in names) else names
    roles: list[WorkerRole] = []
    for name in selected:
        factory = REGISTRY.get(name)
        if factory is None:
            logger.warning("worker.unknown_role", role=name)
            continue
        roles.append(factory(ctx))
    return roles
