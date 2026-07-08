"""Per-route rate limiting as a FastAPI dependency (sliding window, Redis-backed)."""

from __future__ import annotations

import time
from collections.abc import Callable, Coroutine
from typing import Any

import structlog
from fastapi import Request

from algo_platform.api.dependencies.core import RedisDep
from algo_platform.shared.domain.errors import RateLimited
from algo_platform.shared.infrastructure.rate_limiting import RateLimiter, RateLimitRule
from algo_platform.shared.infrastructure.rate_limiting.redis_store import RedisWindowStore

logger = structlog.get_logger(__name__)


def rate_limit(
    name: str, *, times: int, seconds: int, burst: int | None = None
) -> Callable[[Request, RedisDep], Coroutine[Any, Any, None]]:
    """Limit ``times`` requests per ``seconds`` per client IP for this route.

    Fails open (allows the request) if Redis is unavailable so an outage of the
    limiter never takes down the API.
    """
    rule = RateLimitRule(limit=times, window_seconds=seconds, burst_limit=burst)

    async def dependency(request: Request, redis: RedisDep) -> None:
        client_ip = request.client.host if request.client else "unknown"
        limiter = RateLimiter(RedisWindowStore(redis))
        try:
            result = await limiter.check(
                f"rl:{name}:{client_ip}", rule, now_ms=int(time.time() * 1000)
            )
        except Exception:
            logger.warning("rate_limit.unavailable", limiter=name)
            return
        if not result.allowed:
            raise RateLimited(retry_after_seconds=result.retry_after_seconds)

    return dependency
