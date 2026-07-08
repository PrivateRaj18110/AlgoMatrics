"""Email worker role: deliver the transactional e-mail outbox.

Extracted from the original worker loop. Sends pending outbox e-mails and marks
each sent/failed with retry accounting.
"""

from __future__ import annotations

import asyncio
import contextlib

import structlog

from algo_platform.processes.workers.base import WorkerContext
from algo_platform.shared.domain.types import utc_now
from algo_platform.shared.infrastructure.email_outbox import (
    fetch_pending_emails,
    mark_email_failed,
    mark_email_sent,
)

logger = structlog.get_logger("worker.email")

HEARTBEAT_KEY = "hb:email"


class EmailWorker:
    name = "email"

    def __init__(self, ctx: WorkerContext) -> None:
        self._ctx = ctx

    async def run(self, stop: asyncio.Event) -> None:
        ctx = self._ctx
        while not stop.is_set():
            delivered = 0
            try:
                async with ctx.session_factory() as session:
                    emails = await fetch_pending_emails(session)
                    for email in emails:
                        try:
                            await ctx.email_sender.send(email.message())
                        except Exception as exc:
                            mark_email_failed(email, exc)
                            logger.exception(
                                "email.delivery_failed",
                                email_id=str(email.id),
                                attempt=email.attempts,
                            )
                        else:
                            mark_email_sent(email)
                            delivered += 1
                    await session.commit()
            except Exception:
                logger.exception("email.outbox_failed")
                await asyncio.sleep(2)
            if delivered:
                logger.info("email.delivered", count=delivered)
            await ctx.redis.set_str(HEARTBEAT_KEY, utc_now().isoformat(), ttl_seconds=120)
            if delivered == 0:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=ctx.settings.outbox_poll_seconds)
