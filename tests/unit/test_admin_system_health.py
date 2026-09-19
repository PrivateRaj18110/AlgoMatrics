"""The platform-admin health probe that feeds the operations wallboard.

No database or Redis: small fakes stand in for the session and gateway, so the
tests exercise the route function's own decisions — per-service heartbeat ages,
probe latencies, and staying up when a dependency is down.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from algo_platform.api.routes.admin import system_health
from algo_platform.shared.domain.types import utc_now
from algo_platform.shared.infrastructure.heartbeats import service_heartbeats

SETTINGS = SimpleNamespace(scheduler_interval_seconds=60.0, outbox_poll_seconds=1.0)


class FakeSession:
    def __init__(self, *, fail: bool = False, count: int = 3) -> None:
        self.fail = fail
        self.count = count

    async def execute(self, _statement: Any) -> Any:
        if self.fail:
            raise ConnectionError("database down")
        return SimpleNamespace(scalar_one=lambda: self.count)


class FakeRedis:
    def __init__(self, beats: dict[str, float], *, fail: bool = False) -> None:
        now = utc_now()
        self.values = {
            key: (now - timedelta(seconds=age)).isoformat() for key, age in beats.items()
        }
        self.fail = fail

    async def ping(self) -> bool:
        if self.fail:
            raise ConnectionError("redis down")
        return True

    async def get_str(self, key: str) -> str | None:
        return self.values.get(key)


async def _call(session: FakeSession, redis: FakeRedis) -> Any:
    return await system_health(
        admin=SimpleNamespace(),  # type: ignore[arg-type]
        session=session,  # type: ignore[arg-type]
        redis=redis,  # type: ignore[arg-type]
        settings=SETTINGS,  # type: ignore[arg-type]
    )


async def test_reports_every_background_service_with_its_heartbeat_age() -> None:
    result = await _call(
        FakeSession(count=4),
        FakeRedis({"hb:market_data": 2, "hb:trading_engine": 6, "hb:scheduler": 40, "hb:relay": 1}),
    )

    assert result.database is True
    assert result.redis is True
    assert result.database_latency_ms is not None
    assert result.redis_latency_ms is not None
    assert result.outbox_backlog == 4
    assert result.active_runs == 4
    assert result.checked_at is not None

    by_name = {service.name: service for service in result.services}
    assert set(by_name) == {"market_data", "trading_engine", "scheduler", "relay", "email"}
    assert by_name["market_data"].age_seconds == pytest.approx(2, abs=1)
    assert by_name["scheduler"].age_seconds == pytest.approx(40, abs=1)
    # A process whose key is absent has no age — never a made-up zero.
    assert by_name["email"].age_seconds is None
    # The legacy fields stay populated for the admin page.
    assert result.market_data_age_seconds == by_name["market_data"].age_seconds
    assert result.engine_heartbeat_age_seconds == by_name["trading_engine"].age_seconds


async def test_stays_up_and_says_so_when_redis_is_down() -> None:
    result = await _call(FakeSession(), FakeRedis({"hb:market_data": 1}, fail=True))

    assert result.redis is False
    assert result.redis_latency_ms is None
    assert all(service.age_seconds is None for service in result.services)
    assert result.database is True


async def test_stays_up_and_says_so_when_the_database_is_down() -> None:
    result = await _call(FakeSession(fail=True), FakeRedis({"hb:market_data": 1}))

    assert result.database is False
    assert result.database_latency_ms is None
    assert result.outbox_backlog == 0
    assert result.redis is True


def test_stale_thresholds_follow_each_process_loop() -> None:
    slow = SimpleNamespace(scheduler_interval_seconds=600.0, outbox_poll_seconds=30.0)
    thresholds = {name: stale for name, _label, stale in service_heartbeats(slow)}
    assert thresholds["scheduler"] == 1800
    assert thresholds["relay"] == 150
    assert thresholds["market_data"] == 30
