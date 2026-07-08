"""Redis fixed-window rate limiting as a route dependency."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

import structlog
from fastapi import Request

from algo_platform.api.dependencies.core import RedisDep
from algo_platform.shared.domain.errors import RateLimited

logger = structlog.get_logger(__name__)


def rate_limit(
    name: str, *, times: int, seconds: int
) -> Callable[[Request, RedisDep], Coroutine[Any, Any, None]]:
    async def dependency(request: Request, redis: RedisDep) -> None:
        client_ip = request.client.host if request.client else "unknown"
        key = f"rl:{name}:{client_ip}"
        try:
            count = await redis.incr_fixed_window(key, seconds)
        except Exception:
            logger.warning("rate_limit.unavailable", limiter=name)
            return
        if count > times:
            raise RateLimited(retry_after_seconds=seconds)

    return dependency
