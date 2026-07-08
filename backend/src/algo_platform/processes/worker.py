"""Worker process: runs the selected background worker roles.

Historically a single loop that relayed the outbox and delivered e-mail. It is
now a thin host that builds shared resources and runs the roles selected by
``WORKER_ROLES`` (default ``["all"]``), supervised by the runner. Deploy a busy
role to its own container simply by setting ``WORKER_ROLES`` for that service.
"""

from __future__ import annotations

import asyncio
import signal

import structlog

from algo_platform.config import get_settings
from algo_platform.processes.workers.base import WorkerContext
from algo_platform.processes.workers.registry import build_roles
from algo_platform.processes.workers.runner import run_workers
from algo_platform.shared.infrastructure.database import (
    create_engine,
    create_session_factory,
)
from algo_platform.shared.infrastructure.email import create_email_sender
from algo_platform.shared.infrastructure.event_bus_factory import build_event_bus
from algo_platform.shared.infrastructure.metrics_server import start_process_metrics
from algo_platform.shared.infrastructure.redis_gateway import RedisGateway
from algo_platform.shared.infrastructure.telemetry import configure_logging

logger = structlog.get_logger("worker")


async def run() -> None:
    settings = get_settings()
    configure_logging(level=settings.log_level, env=settings.app_env, service="algo-worker")
    engine = create_engine(settings.database_url, pool_size=4)
    redis = RedisGateway.from_url(settings.redis_url)
    context = WorkerContext(
        settings=settings,
        session_factory=create_session_factory(engine),
        redis=redis,
        event_bus=build_event_bus(settings, redis),
        email_sender=create_email_sender(settings),
        metrics=start_process_metrics(settings, "algo-worker"),
    )
    roles = build_roles(settings.worker_roles, context)
    stop_event = asyncio.Event()
    _install_signal_handlers(stop_event)
    logger.info("worker.started", roles=[role.name for role in roles])
    try:
        await run_workers(roles, stop_event)
    finally:
        await redis.close()
        await engine.dispose()
        logger.info("worker.stopped")


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_event_loop()
    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_: stop_event.set())


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
