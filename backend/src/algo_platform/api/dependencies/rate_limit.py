"""Rate limiting as FastAPI dependencies (sliding window, Redis-backed).

Two forms:

- :func:`rate_limit` — per-IP limit for a named route (used by auth endpoints).
- :func:`scoped_rate_limit` — multi-scope limit (tenant/user/api-key/ip/broker/
  route); a request is denied if *any* applicable scope is exceeded.

Both honour admin overrides and bypasses, and fail open if Redis is unavailable.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Coroutine
from typing import Any

import structlog
from fastapi import Request

from algo_platform.api.dependencies.core import RedisDep
from algo_platform.api.dependencies.tenant import TenantDep
from algo_platform.shared.domain.errors import RateLimited
from algo_platform.shared.infrastructure.rate_limiting import RateLimiter, RateLimitRule
from algo_platform.shared.infrastructure.rate_limiting.overrides import RateLimitOverrides
from algo_platform.shared.infrastructure.rate_limiting.redis_store import RedisWindowStore
from algo_platform.shared.infrastructure.rate_limiting.scopes import Scope, scope_keys

logger = structlog.get_logger(__name__)


def rate_limit(
    name: str, *, times: int, seconds: int, burst: int | None = None
) -> Callable[[Request, RedisDep], Coroutine[Any, Any, None]]:
    """Limit ``times`` requests per ``seconds`` per client IP for this route."""
    default_rule = RateLimitRule(limit=times, window_seconds=seconds, burst_limit=burst)

    async def dependency(request: Request, redis: RedisDep) -> None:
        client_ip = request.client.host if request.client else "unknown"
        overrides = RateLimitOverrides(redis)
        limiter = RateLimiter(RedisWindowStore(redis))
        try:
            if await overrides.is_bypassed(Scope.IP, client_ip):
                return
            rule = await overrides.rule_for(name, default_rule)
            result = await limiter.check(
                f"rl:{name}:{client_ip}", rule, now_ms=int(time.time() * 1000)
            )
        except Exception:
            logger.warning("rate_limit.unavailable", limiter=name)
            return
        if not result.allowed:
            raise RateLimited(retry_after_seconds=result.retry_after_seconds)

    return dependency


def scoped_rate_limit(
    name: str,
    *,
    times: int,
    seconds: int,
    burst: int | None = None,
    scopes: tuple[Scope, ...] = (Scope.TENANT, Scope.USER),
    broker_param: str | None = None,
) -> Callable[..., Coroutine[Any, Any, None]]:
    """Limit a route across the given scopes (tenant/user/api-key/ip/broker/route)."""
    default_rule = RateLimitRule(limit=times, window_seconds=seconds, burst_limit=burst)

    async def dependency(request: Request, redis: RedisDep, tenant: TenantDep) -> None:
        overrides = RateLimitOverrides(redis)
        limiter = RateLimiter(RedisWindowStore(redis))
        subjects = _subjects(request, tenant, scopes, name, broker_param)
        now_ms = int(time.time() * 1000)
        try:
            rule = await overrides.rule_for(name, default_rule)
            for scope, key in scope_keys(name, subjects):
                if await overrides.is_bypassed(scope, subjects[scope] or ""):
                    continue
                result = await limiter.check(key, rule, now_ms=now_ms)
                if not result.allowed:
                    raise RateLimited(retry_after_seconds=result.retry_after_seconds)
        except RateLimited:
            raise
        except Exception:
            logger.warning("rate_limit.unavailable", limiter=name)
            return

    return dependency


def _subjects(
    request: Request,
    tenant: TenantDep,
    scopes: tuple[Scope, ...],
    name: str,
    broker_param: str | None,
) -> dict[Scope, str | None]:
    api_key = request.headers.get("X-API-Key")
    resolved: dict[Scope, str | None] = {
        Scope.TENANT: str(tenant.organization_id),
        Scope.USER: str(tenant.user.user_id),
        Scope.API_KEY: (
            hashlib.sha256(api_key.encode()).hexdigest()[:32] if api_key else None
        ),
        Scope.IP: request.client.host if request.client else None,
        Scope.ROUTE: name,
        Scope.BROKER: (
            str(request.path_params.get(broker_param)) if broker_param else None
        ),
    }
    return {scope: resolved.get(scope) for scope in scopes}
