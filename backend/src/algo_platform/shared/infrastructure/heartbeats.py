"""Heartbeats written by the background processes, and how late each may be.

Every long-running process writes ``hb:<name>`` (an ISO timestamp) to Redis on
each loop. The admin health endpoint, the wallboard and the daily briefing all
read them through here so they agree on names and thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from algo_platform.shared.domain.types import utc_now
from algo_platform.shared.infrastructure.redis_gateway import RedisGateway


@dataclass(frozen=True, slots=True)
class Heartbeat:
    name: str
    label: str
    age_seconds: float | None
    stale_after_seconds: int

    @property
    def state(self) -> str:
        """ok | overdue | missing."""
        if self.age_seconds is None:
            return "missing"
        return "ok" if self.age_seconds <= self.stale_after_seconds else "overdue"


def service_heartbeats(settings: Any) -> tuple[tuple[str, str, int], ...]:
    """(redis key suffix, label, stale-after seconds) for every background process.

    Thresholds allow a few missed loop periods before a process is called overdue.
    """
    scheduler_every = float(getattr(settings, "scheduler_interval_seconds", 60.0))
    outbox_every = float(getattr(settings, "outbox_poll_seconds", 1.0))
    return (
        ("market_data", "Market data feed", 30),
        ("trading_engine", "Trading engine", 30),
        ("scheduler", "Scheduler", max(180, int(scheduler_every * 3))),
        ("relay", "Outbox relay", max(60, int(outbox_every * 5))),
        ("email", "E-mail worker", max(60, int(outbox_every * 5))),
    )


async def heartbeat_age(redis: RedisGateway, key: str) -> float | None:
    raw = await redis.get_str(key)
    if raw is None:
        return None
    try:
        then = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return max(0.0, (utc_now() - then).total_seconds())


async def read_heartbeats(redis: RedisGateway, settings: Any) -> list[Heartbeat]:
    return [
        Heartbeat(name, label, await heartbeat_age(redis, f"hb:{name}"), stale_after)
        for name, label, stale_after in service_heartbeats(settings)
    ]
