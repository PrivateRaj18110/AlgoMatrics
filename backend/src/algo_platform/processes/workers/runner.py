"""Supervise a set of worker roles within one process.

Each role runs until the shared stop event is set. A role that crashes is
restarted with a short backoff so one failing role cannot take down the others
or the process. Running multiple roles in one process keeps small deployments
simple; scaling a busy role to its own container is just a different role set.
"""

from __future__ import annotations

import asyncio
import contextlib

import structlog

from algo_platform.processes.workers.base import WorkerRole

logger = structlog.get_logger("worker.runner")


async def _supervise(role: WorkerRole, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await role.run(stop)
            return  # clean exit because stop was set
        except Exception:
            logger.exception("worker.role_crashed", role=role.name)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=2)


async def run_workers(roles: list[WorkerRole], stop: asyncio.Event) -> None:
    if not roles:
        logger.warning("worker.no_roles_selected")
        return
    logger.info("worker.roles_started", roles=[role.name for role in roles])
    await asyncio.gather(*(_supervise(role, stop) for role in roles))
