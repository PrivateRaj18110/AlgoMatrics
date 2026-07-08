"""Unit tests for feature-flag evaluation (Phase 4, slice A)."""

from __future__ import annotations

from uuid import UUID

from algo_platform.modules.feature_flags.domain.flags import (
    EvaluationContext,
    FlagDefinition,
    FlagOverride,
    ScopeType,
    evaluate,
)

_ORG = UUID("11111111-1111-1111-1111-111111111111")
_USER = UUID("22222222-2222-2222-2222-222222222222")


def _flag(**over: object) -> FlagDefinition:
    base = {"key": "marketplace", "enabled": True, "kill_switch": False, "rollout_percentage": 100}
    base.update(over)
    return FlagDefinition(**base)  # type: ignore[arg-type]


def _ctx(**over: object) -> EvaluationContext:
    base: dict[str, object] = {
        "environment": "production",
        "organization_id": _ORG,
        "user_id": _USER,
    }
    base.update(over)
    return EvaluationContext(**base)  # type: ignore[arg-type]


def test_enabled_flag_is_on() -> None:
    assert evaluate(_flag(), [], _ctx()) is True


def test_disabled_flag_is_off() -> None:
    assert evaluate(_flag(enabled=False), [], _ctx()) is False


def test_kill_switch_overrides_everything() -> None:
    overrides = [FlagOverride(ScopeType.USER, str(_USER), enabled=True)]
    assert evaluate(_flag(enabled=True, kill_switch=True), overrides, _ctx()) is False


def test_user_override_beats_tenant_and_env() -> None:
    overrides = [
        FlagOverride(ScopeType.USER, str(_USER), enabled=False),
        FlagOverride(ScopeType.TENANT, str(_ORG), enabled=True),
        FlagOverride(ScopeType.ENVIRONMENT, "production", enabled=True),
    ]
    assert evaluate(_flag(enabled=True), overrides, _ctx()) is False


def test_tenant_override_beats_env() -> None:
    overrides = [
        FlagOverride(ScopeType.TENANT, str(_ORG), enabled=False),
        FlagOverride(ScopeType.ENVIRONMENT, "production", enabled=True),
    ]
    assert evaluate(_flag(enabled=True), overrides, _ctx(user_id=None)) is False


def test_environment_override_applies() -> None:
    overrides = [FlagOverride(ScopeType.ENVIRONMENT, "production", enabled=True)]
    ctx = _ctx(user_id=None, organization_id=None)
    assert evaluate(_flag(enabled=False), overrides, ctx) is True


def test_zero_percent_rollout_is_off() -> None:
    assert evaluate(_flag(rollout_percentage=0), [], _ctx()) is False


def test_full_rollout_is_on() -> None:
    assert evaluate(_flag(rollout_percentage=100), [], _ctx()) is True


def test_partial_rollout_is_deterministic_and_bounded() -> None:
    flag = _flag(rollout_percentage=50)
    # Same subject → same decision every time.
    first = evaluate(flag, [], _ctx())
    assert evaluate(flag, [], _ctx()) == first
    # Across many users the on-rate is roughly the rollout percentage.
    on = 0
    total = 400
    for i in range(total):
        uid = UUID(int=i, version=4)
        if evaluate(flag, [], EvaluationContext(environment="production", user_id=uid)):
            on += 1
    assert 0.35 * total <= on <= 0.65 * total


def test_rollout_without_subject_is_off() -> None:
    ctx = EvaluationContext(environment="production", organization_id=None, user_id=None)
    assert evaluate(_flag(rollout_percentage=50), [], ctx) is False
