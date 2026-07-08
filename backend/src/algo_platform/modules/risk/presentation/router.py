from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from algo_platform.api.dependencies.core import SessionDep
from algo_platform.api.dependencies.pagination import PageDep
from algo_platform.api.dependencies.tenant import TenantContext, require_permission
from algo_platform.modules.audit.application.service import AuditService
from algo_platform.modules.organizations.domain.roles import Permission
from algo_platform.modules.risk.application.service import RiskService
from algo_platform.modules.risk.domain.limits import KillSwitchScope

router = APIRouter(prefix="/risk", tags=["risk"])

RiskViewTenant = Annotated[TenantContext, Depends(require_permission(Permission.RISK_VIEW))]
RiskManageTenant = Annotated[TenantContext, Depends(require_permission(Permission.RISK_MANAGE))]


def get_risk_service(session: SessionDep) -> RiskService:
    return RiskService(session)


RiskServiceDep = Annotated[RiskService, Depends(get_risk_service)]


class RiskLimitsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID | None
    max_order_quantity: Decimal
    max_order_value: Decimal
    max_daily_loss: Decimal
    max_open_positions: int
    max_exposure_value: Decimal
    max_drawdown_pct: Decimal
    is_active: bool
    updated_at: datetime


class UpdateRiskLimitsRequest(BaseModel):
    max_order_quantity: Decimal | None = Field(default=None, gt=0)
    max_order_value: Decimal | None = Field(default=None, gt=0)
    max_daily_loss: Decimal | None = Field(default=None, gt=0)
    max_open_positions: int | None = Field(default=None, ge=1, le=10_000)
    max_exposure_value: Decimal | None = Field(default=None, gt=0)
    max_drawdown_pct: Decimal | None = Field(default=None, gt=0, le=100)
    is_active: bool | None = None


class KillSwitchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    scope: str
    scope_ref: str
    reason: str
    engaged_by: UUID
    engaged_at: datetime
    released_at: datetime | None


class EngageKillSwitchRequest(BaseModel):
    scope: Literal["organization", "account", "strategy"]
    scope_ref: str = Field(default="", max_length=64)
    reason: str = Field(min_length=3, max_length=300)


class RiskEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID | None
    strategy_run_id: UUID | None
    event_type: str
    severity: str
    message: str
    details: dict[str, Any]
    occurred_at: datetime


class PagedRiskEventsResponse(BaseModel):
    items: list[RiskEventResponse]
    total: int


class MessageResponse(BaseModel):
    message: str


@router.get("/limits", response_model=list[RiskLimitsResponse])
async def list_limits(tenant: RiskViewTenant, service: RiskServiceDep) -> list[RiskLimitsResponse]:
    limits = await service.list_limits(tenant.organization_id)
    return [RiskLimitsResponse.model_validate(entry) for entry in limits]


@router.patch("/limits/{limits_id}", response_model=RiskLimitsResponse)
async def update_limits(
    limits_id: UUID,
    payload: UpdateRiskLimitsRequest,
    request: Request,
    tenant: RiskManageTenant,
    service: RiskServiceDep,
    session: SessionDep,
) -> RiskLimitsResponse:
    changes = {k: v for k, v in payload.model_dump().items() if v is not None}
    updated = await service.update_limits(tenant.organization_id, limits_id, changes)
    await AuditService(session).record(
        action="risk.limits_updated",
        resource_type="risk_limits",
        resource_id=str(limits_id),
        organization_id=tenant.organization_id,
        actor_user_id=tenant.user.user_id,
        request_id=getattr(request.state, "request_id", None),
        after_state={k: str(v) for k, v in changes.items()},
    )
    return RiskLimitsResponse.model_validate(updated)


@router.get("/kill-switches", response_model=list[KillSwitchResponse])
async def list_kill_switches(
    tenant: RiskViewTenant,
    service: RiskServiceDep,
    include_released: Annotated[bool, Query()] = False,
) -> list[KillSwitchResponse]:
    switches = await service.list_kill_switches(
        tenant.organization_id, include_released=include_released
    )
    return [KillSwitchResponse.model_validate(s) for s in switches]


@router.post(
    "/kill-switches", response_model=KillSwitchResponse, status_code=status.HTTP_201_CREATED
)
async def engage_kill_switch(
    payload: EngageKillSwitchRequest,
    request: Request,
    tenant: RiskManageTenant,
    service: RiskServiceDep,
    session: SessionDep,
) -> KillSwitchResponse:
    switch = await service.engage_kill_switch(
        tenant.organization_id,
        scope=KillSwitchScope(payload.scope),
        scope_ref=payload.scope_ref,
        reason=payload.reason,
        engaged_by=tenant.user.user_id,
    )
    await AuditService(session).record(
        action="risk.kill_switch_engaged",
        resource_type="kill_switch",
        resource_id=str(switch.id),
        organization_id=tenant.organization_id,
        actor_user_id=tenant.user.user_id,
        request_id=getattr(request.state, "request_id", None),
        after_state={"scope": payload.scope, "reason": payload.reason},
    )
    return KillSwitchResponse.model_validate(switch)


@router.delete("/kill-switches/{switch_id}", response_model=MessageResponse)
async def release_kill_switch(
    switch_id: UUID,
    request: Request,
    tenant: RiskManageTenant,
    service: RiskServiceDep,
    session: SessionDep,
) -> MessageResponse:
    await service.release_kill_switch(
        tenant.organization_id, switch_id, released_by=tenant.user.user_id
    )
    await AuditService(session).record(
        action="risk.kill_switch_released",
        resource_type="kill_switch",
        resource_id=str(switch_id),
        organization_id=tenant.organization_id,
        actor_user_id=tenant.user.user_id,
        request_id=getattr(request.state, "request_id", None),
    )
    return MessageResponse(message="kill switch released")


@router.get("/violations", response_model=PagedRiskEventsResponse)
async def list_violations(
    tenant: RiskViewTenant, service: RiskServiceDep, page: PageDep
) -> PagedRiskEventsResponse:
    events, total = await service.list_events(
        tenant.organization_id, limit=page.limit, offset=page.offset
    )
    return PagedRiskEventsResponse(
        items=[RiskEventResponse.model_validate(e) for e in events], total=total
    )
