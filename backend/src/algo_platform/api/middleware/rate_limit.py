"""Global per-IP sliding-window rate limiting.

Coarse protection in front of per-route dependency limits and any upstream nginx
limits. Reads the shared :class:`RateLimiter` and its rule from application state
(built in the API lifespan), fails open on limiter errors, and emits standard
``X-RateLimit-*`` / ``Retry-After`` headers. Route-, tenant-, user-, api-key-,
and broker-scoped limits are applied by dependencies where those identities are
resolved; this middleware owns the per-IP scope.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from algo_platform.api.middleware.errors import problem_response
from algo_platform.shared.infrastructure.rate_limiting import RateLimiter, RateLimitRule
from algo_platform.shared.infrastructure.rate_limiting.overrides import RateLimitOverrides
from algo_platform.shared.infrastructure.rate_limiting.scopes import Scope

logger = structlog.get_logger("rate_limit")

# Health/metrics probes must never be throttled.
_EXEMPT_PREFIXES = ("/api/v1/health", "/metrics")


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, rule: RateLimitRule) -> None:
        super().__init__(app)
        self._rule = rule

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path.startswith(_EXEMPT_PREFIXES):
            return await call_next(request)
        limiter: RateLimiter | None = getattr(request.app.state, "rate_limiter", None)
        if limiter is None:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        redis = getattr(request.app.state, "redis", None)
        try:
            if redis is not None:
                overrides = RateLimitOverrides(redis)
                if await overrides.is_bypassed(Scope.IP, client_ip):
                    return await call_next(request)
                rule = await overrides.rule_for("ip", self._rule)
            else:
                rule = self._rule
            result = await limiter.check(
                f"rl:ip:{client_ip}", rule, now_ms=int(time.time() * 1000)
            )
        except Exception:
            logger.warning("rate_limit.ip_check_failed")
            return await call_next(request)

        if not result.allowed:
            blocked = problem_response(
                request,
                status_code=429,
                title="rate limited",
                detail="Too many requests. Slow down and retry later.",
                code="rate_limited",
            )
            blocked.headers["Retry-After"] = str(result.retry_after_seconds)
            blocked.headers["X-RateLimit-Limit"] = str(result.limit)
            blocked.headers["X-RateLimit-Remaining"] = "0"
            return blocked

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(result.limit)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        return response
