"""Feature-flag HTTP surface: tenant evaluation + platform-admin management."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Path
from pydantic import BaseModel, Field

from algo_platform.api.dependencies.auth import PlatformAdminDep
from algo_platform.api.dependencies.core import RedisDep, SessionDep, SettingsDep
from algo_platform.api.dependencies.tenant import TenantDep
from algo_platform.modules.audit.application.service import AuditService
from algo_platform.modules.feature_flags.application.service import FeatureFlagService
from algo_platform.modules.feature_flags.domain.flags import EvaluationContext, ScopeType
from algo_platform.shared.domain.errors import ValidationFailed

router = APIRouter(prefix="/feature-flags", tags=["feature-flags"])
admin_router = APIRouter(prefix="/admin/feature-flags", tags=["admin", "feature-flags"])


def _context(settings: SettingsDep, tenant: TenantDep) -> EvaluationContext:
    return EvaluationContext(
        environment=settings.app_env,
        organization_id=tenant.organization_id,
        user_id=tenant.user.user_id,
    )


@router.get("", response_model=dict[str, bool])
async def evaluate_flags(
    tenant: TenantDep, session: SessionDep, redis: RedisDep, settings: SettingsDep
) -> dict[str, bool]:
    """Evaluate every flag for the caller's environment/tenant/user."""
    service = FeatureFlagService(session, redis)
    return await service.evaluate_all(_context(settings, tenant))


# -- admin management ------------------------------------------------------


class FlagResponse(BaseModel):
    key: str
    description: str
    enabled: bool
    kill_switch: bool
    rollout_percentage: int


class FlagUpsertRequest(BaseModel):
    description: str = Field(default="", max_length=255)
    enabled: bool = False
    kill_switch: bool = False
    rollout_percentage: int = Field(default=100, ge=0, le=100)


class OverrideResponse(BaseModel):
    scope_type: str
    scope_id: str
    enabled: bool


class OverrideRequest(BaseModel):
    scope_type: ScopeType
    scope_id: str = Field(min_length=1, max_length=64)
    enabled: bool


@admin_router.get("", response_model=list[FlagResponse])
async def list_flags(admin: PlatformAdminDep, session: SessionDep) -> list[FlagResponse]:
    flags = await FeatureFlagService(session).list_flags()
    return [FlagResponse(**asdict(flag)) for flag in flags]


@admin_router.put("/{key}", response_model=FlagResponse)
async def upsert_flag(
    admin: PlatformAdminDep,
    session: SessionDep,
    redis: RedisDep,
    payload: FlagUpsertRequest,
    key: Annotated[str, Path(min_length=1, max_length=80)],
) -> FlagResponse:
    service = FeatureFlagService(session, redis)
    await service.upsert_flag(
        key=key,
        description=payload.description,
        enabled=payload.enabled,
        kill_switch=payload.kill_switch,
        rollout_percentage=payload.rollout_percentage,
    )
    await AuditService(session).record(
        action="admin.feature_flag_updated",
        resource_type="feature_flag",
        resource_id=key,
        actor_user_id=admin.user_id,
        actor_type="admin",
        after_state=payload.model_dump(),
    )
    return FlagResponse(key=key, **payload.model_dump())


@admin_router.get("/{key}/overrides", response_model=list[OverrideResponse])
async def list_overrides(
    admin: PlatformAdminDep,
    session: SessionDep,
    key: Annotated[str, Path(min_length=1, max_length=80)],
) -> list[OverrideResponse]:
    overrides = await FeatureFlagService(session).list_overrides(key)
    return [OverrideResponse(**asdict(o)) for o in overrides]


@admin_router.put("/{key}/overrides", status_code=204)
async def set_override(
    admin: PlatformAdminDep,
    session: SessionDep,
    redis: RedisDep,
    payload: OverrideRequest,
    key: Annotated[str, Path(min_length=1, max_length=80)],
) -> None:
    service = FeatureFlagService(session, redis)
    await service.set_override(
        flag_key=key,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        enabled=payload.enabled,
    )
    await AuditService(session).record(
        action="admin.feature_flag_override_set",
        resource_type="feature_flag",
        resource_id=key,
        actor_user_id=admin.user_id,
        actor_type="admin",
        after_state=payload.model_dump(),
    )


@admin_router.delete("/{key}/overrides", status_code=204)
async def clear_override(
    admin: PlatformAdminDep,
    session: SessionDep,
    redis: RedisDep,
    payload: OverrideRequest,
    key: Annotated[str, Path(min_length=1, max_length=80)],
) -> None:
    if not payload.scope_id:
        raise ValidationFailed("scope_id is required")
    service = FeatureFlagService(session, redis)
    await service.clear_override(
        flag_key=key, scope_type=payload.scope_type, scope_id=payload.scope_id
    )
    await AuditService(session).record(
        action="admin.feature_flag_override_cleared",
        resource_type="feature_flag",
        resource_id=key,
        actor_user_id=admin.user_id,
        actor_type="admin",
        before_state=payload.model_dump(),
    )
