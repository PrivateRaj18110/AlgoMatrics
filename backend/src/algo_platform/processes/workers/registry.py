"""Registry of worker roles and selection from configuration."""

from __future__ import annotations

from collections.abc import Callable

import structlog

from algo_platform.processes.workers.base import WorkerContext, WorkerRole
from algo_platform.processes.workers.email import EmailWorker
from algo_platform.processes.workers.relay import OutboxRelayWorker

logger = structlog.get_logger("worker.registry")

WorkerFactory = Callable[[WorkerContext], WorkerRole]

# Name -> factory. Slice B registers the event-consuming domain workers here.
REGISTRY: dict[str, WorkerFactory] = {
    OutboxRelayWorker.name: OutboxRelayWorker,
    EmailWorker.name: EmailWorker,
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
