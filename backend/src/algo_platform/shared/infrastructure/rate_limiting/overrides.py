"""Admin-configurable rate-limit overrides and bypasses (Redis-backed).

Operators can raise/lower a named limit or exempt a specific subject at runtime
without a deployment. Overrides are keyed by the limiter ``name``; bypasses are
keyed by scope + subject id. Lookups fail open (return the default / not
bypassed) so a Redis hiccup never blocks traffic through the limiter config.
"""

from __future__ import annotations

from algo_platform.shared.infrastructure.rate_limiting.limiter import RateLimitRule
from algo_platform.shared.infrastructure.rate_limiting.scopes import Scope
from algo_platform.shared.infrastructure.redis_gateway import RedisGateway


def _rule_key(name: str) -> str:
    return f"rl:cfg:{name}"


def _bypass_key(scope: Scope, subject: str) -> str:
    return f"rl:bypass:{scope.value}:{subject}"


class RateLimitOverrides:
    def __init__(self, redis: RedisGateway) -> None:
        self._redis = redis

    async def rule_for(self, name: str, default: RateLimitRule) -> RateLimitRule:
        try:
            raw = await self._redis.get_json(_rule_key(name))
        except Exception:
            return default
        if not raw:
            return default
        try:
            return RateLimitRule(
                limit=int(raw["limit"]),
                window_seconds=int(raw["window_seconds"]),
                burst_limit=(int(raw["burst_limit"]) if raw.get("burst_limit") else None),
                burst_window_seconds=int(raw.get("burst_window_seconds", 1)),
            )
        except (KeyError, ValueError, TypeError):
            return default

    async def set_rule(self, name: str, rule: RateLimitRule) -> None:
        await self._redis.set_json(
            _rule_key(name),
            {
                "limit": rule.limit,
                "window_seconds": rule.window_seconds,
                "burst_limit": rule.burst_limit,
                "burst_window_seconds": rule.burst_window_seconds,
            },
        )

    async def clear_rule(self, name: str) -> None:
        await self._redis.delete(_rule_key(name))

    async def is_bypassed(self, scope: Scope, subject: str) -> bool:
        try:
            return await self._redis.get_str(_bypass_key(scope, subject)) is not None
        except Exception:
            return False

    async def set_bypass(self, scope: Scope, subject: str) -> None:
        await self._redis.set_str(_bypass_key(scope, subject), "1")

    async def clear_bypass(self, scope: Scope, subject: str) -> None:
        await self._redis.delete(_bypass_key(scope, subject))
