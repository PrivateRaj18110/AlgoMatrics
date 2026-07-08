"""Unit tests for rate-limit scopes and admin overrides (Phase 5, slice C)."""

from __future__ import annotations

from typing import Any

from algo_platform.shared.infrastructure.rate_limiting import RateLimitRule
from algo_platform.shared.infrastructure.rate_limiting.overrides import RateLimitOverrides
from algo_platform.shared.infrastructure.rate_limiting.scopes import Scope, scope_keys


def test_scope_keys_skips_missing_subjects() -> None:
    keys = scope_keys(
        "orders",
        {Scope.TENANT: "org1", Scope.USER: None, Scope.IP: "1.2.3.4"},
    )
    assert keys == [
        (Scope.TENANT, "rl:orders:tenant:org1"),
        (Scope.IP, "rl:orders:ip:1.2.3.4"),
    ]


def test_scope_keys_namespaced_by_name() -> None:
    a = scope_keys("login", {Scope.USER: "u1"})
    b = scope_keys("orders", {Scope.USER: "u1"})
    assert a[0][1] != b[0][1]  # same subject, different limiter budgets


class _FakeRedis:
    def __init__(self) -> None:
        self.json: dict[str, dict[str, Any]] = {}
        self.strings: dict[str, str] = {}

    async def get_json(self, key: str) -> dict[str, Any] | None:
        return self.json.get(key)

    async def set_json(
        self, key: str, value: dict[str, Any], *, ttl_seconds: int | None = None
    ) -> None:
        self.json[key] = value

    async def get_str(self, key: str) -> str | None:
        return self.strings.get(key)

    async def set_str(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        self.strings[key] = value

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.json.pop(key, None)
            self.strings.pop(key, None)


async def test_override_rule_roundtrip_and_default() -> None:
    redis = _FakeRedis()
    overrides = RateLimitOverrides(redis)  # type: ignore[arg-type]
    default = RateLimitRule(limit=10, window_seconds=60)

    # No override configured -> default returned.
    assert await overrides.rule_for("orders", default) == default

    await overrides.set_rule(
        "orders", RateLimitRule(limit=5, window_seconds=30, burst_limit=2)
    )
    resolved = await overrides.rule_for("orders", default)
    assert resolved.limit == 5
    assert resolved.window_seconds == 30
    assert resolved.burst_limit == 2

    await overrides.clear_rule("orders")
    assert await overrides.rule_for("orders", default) == default


async def test_malformed_override_falls_back_to_default() -> None:
    redis = _FakeRedis()
    redis.json["rl:cfg:orders"] = {"limit": "not-a-number"}
    overrides = RateLimitOverrides(redis)  # type: ignore[arg-type]
    default = RateLimitRule(limit=10, window_seconds=60)
    assert await overrides.rule_for("orders", default) == default


async def test_bypass_roundtrip() -> None:
    redis = _FakeRedis()
    overrides = RateLimitOverrides(redis)  # type: ignore[arg-type]
    assert not await overrides.is_bypassed(Scope.IP, "9.9.9.9")
    await overrides.set_bypass(Scope.IP, "9.9.9.9")
    assert await overrides.is_bypassed(Scope.IP, "9.9.9.9")
    await overrides.clear_bypass(Scope.IP, "9.9.9.9")
    assert not await overrides.is_bypassed(Scope.IP, "9.9.9.9")
