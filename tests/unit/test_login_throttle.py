"""Unit test for the account-lockout helpers (no DB, fake Redis)."""

from __future__ import annotations

import pytest

from algo_platform.modules.identity.application.auth_service import (
    LOCKOUT_WINDOW_SECONDS,
    MAX_FAILED_LOGINS,
    AuthService,
    _failed_login_key,
)
from algo_platform.shared.domain.errors import RateLimited


class FakeRedis:
    """Minimal fixed-window counter matching RedisGateway's surface."""

    def __init__(self) -> None:
        self.counters: dict[str, int] = {}

    async def get_str(self, key: str) -> str | None:
        value = self.counters.get(key)
        return None if value is None else str(value)

    async def incr_fixed_window(self, key: str, window_seconds: int) -> int:
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.counters.pop(key, None)


def _service(redis: FakeRedis) -> AuthService:
    # Only the throttle helpers are exercised; other collaborators stay unset.
    service = AuthService.__new__(AuthService)
    service._redis = redis  # type: ignore[attr-defined]
    return service


async def test_lockout_after_max_failures() -> None:
    redis = FakeRedis()
    service = _service(redis)
    email = "victim@example.com"

    for _ in range(MAX_FAILED_LOGINS):
        await service._ensure_not_locked_out(email)  # not yet locked
        await service._record_failed_login(email)

    with pytest.raises(RateLimited) as excinfo:
        await service._ensure_not_locked_out(email)
    assert excinfo.value.retry_after_seconds == LOCKOUT_WINDOW_SECONDS


async def test_success_clears_counter() -> None:
    redis = FakeRedis()
    service = _service(redis)
    email = "user@example.com"
    await service._record_failed_login(email)
    await service._record_failed_login(email)
    assert redis.counters[_failed_login_key(email)] == 2
    await service._clear_failed_logins(email)
    await service._ensure_not_locked_out(email)  # no raise
    assert _failed_login_key(email) not in redis.counters
