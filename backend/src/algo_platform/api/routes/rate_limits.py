"""Platform-admin management of rate-limit overrides and bypasses."""

from __future__ import annotations

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from algo_platform.api.dependencies.auth import PlatformAdminDep
from algo_platform.api.dependencies.core import RedisDep, SessionDep
from algo_platform.modules.audit.application.service import AuditService
from algo_platform.shared.infrastructure.rate_limiting import RateLimitRule
from algo_platform.shared.infrastructure.rate_limiting.overrides import RateLimitOverrides
from algo_platform.shared.infrastructure.rate_limiting.scopes import Scope

router = APIRouter(prefix="/admin/rate-limits", tags=["admin", "rate-limits"])


class RuleBody(BaseModel):
    limit: int = Field(ge=1)
    window_seconds: int = Field(ge=1, le=86_400)
    burst_limit: int | None = Field(default=None, ge=1)
    burst_window_seconds: int = Field(default=1, ge=1, le=3600)


class BypassBody(BaseModel):
    scope: Scope
    subject: str = Field(min_length=1, max_length=128)


@router.put("/config/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def set_override(
    admin: PlatformAdminDep,
    redis: RedisDep,
    session: SessionDep,
    name: str,
    body: RuleBody,
) -> None:
    await RateLimitOverrides(redis).set_rule(
        name,
        RateLimitRule(
            limit=body.limit,
            window_seconds=body.window_seconds,
            burst_limit=body.burst_limit,
            burst_window_seconds=body.burst_window_seconds,
        ),
    )
    await AuditService(session).record(
        action="admin.rate_limit_override_set",
        resource_type="rate_limit",
        resource_id=name,
        actor_user_id=admin.user_id,
        actor_type="admin",
        after_state=body.model_dump(),
    )


@router.delete("/config/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def clear_override(
    admin: PlatformAdminDep, redis: RedisDep, session: SessionDep, name: str
) -> None:
    await RateLimitOverrides(redis).clear_rule(name)
    await AuditService(session).record(
        action="admin.rate_limit_override_cleared",
        resource_type="rate_limit",
        resource_id=name,
        actor_user_id=admin.user_id,
        actor_type="admin",
    )


@router.put("/bypass", status_code=status.HTTP_204_NO_CONTENT)
async def set_bypass(
    admin: PlatformAdminDep, redis: RedisDep, session: SessionDep, body: BypassBody
) -> None:
    await RateLimitOverrides(redis).set_bypass(body.scope, body.subject)
    await AuditService(session).record(
        action="admin.rate_limit_bypass_set",
        resource_type="rate_limit",
        resource_id=f"{body.scope.value}:{body.subject}",
        actor_user_id=admin.user_id,
        actor_type="admin",
        after_state=body.model_dump(),
    )


@router.delete("/bypass", status_code=status.HTTP_204_NO_CONTENT)
async def clear_bypass(
    admin: PlatformAdminDep, redis: RedisDep, session: SessionDep, body: BypassBody
) -> None:
    await RateLimitOverrides(redis).clear_bypass(body.scope, body.subject)
    await AuditService(session).record(
        action="admin.rate_limit_bypass_cleared",
        resource_type="rate_limit",
        resource_id=f"{body.scope.value}:{body.subject}",
        actor_user_id=admin.user_id,
        actor_type="admin",
        before_state=body.model_dump(),
    )
