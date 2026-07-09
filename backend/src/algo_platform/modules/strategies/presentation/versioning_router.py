"""Strategy versioning HTTP API: approvals, diff, validation, deployments."""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from algo_platform.api.dependencies.core import SessionDep
from algo_platform.api.dependencies.tenant import TenantContext, require_permission
from algo_platform.modules.organizations.domain.roles import Permission
from algo_platform.modules.strategies.application.versioning_service import (
    StrategyVersioningService,
)
from algo_platform.modules.strategies.domain.versioning import ApprovalAction

router = APIRouter(tags=["strategy-versioning"])

ViewDep = Annotated[TenantContext, Depends(require_permission(Permission.STRATEGIES_VIEW))]
ManageDep = Annotated[TenantContext, Depends(require_permission(Permission.STRATEGIES_MANAGE))]


class NoteRequest(BaseModel):
    note: str = Field(default="", max_length=1000)


class ApprovalResponse(BaseModel):
    version_id: UUID
    status: str
    review_note: str


class DeployRequest(BaseModel):
    version_id: UUID
    action: str = Field(default="deploy", pattern="^(deploy|rollback)$")


async def _act(
    session: SessionDep, tenant: TenantContext, version_id: UUID, action: ApprovalAction, note: str
) -> ApprovalResponse:
    dto = await StrategyVersioningService(session).act(
        tenant.organization_id,
        version_id,
        action=action,
        actor=tenant.user.user_id,
        note=note,
    )
    return ApprovalResponse(
        version_id=dto.version_id, status=dto.status, review_note=dto.review_note
    )


@router.post("/strategy-versions/{version_id}/submit", response_model=ApprovalResponse)
async def submit(
    version_id: UUID, payload: NoteRequest, tenant: ManageDep, session: SessionDep
) -> ApprovalResponse:
    return await _act(session, tenant, version_id, ApprovalAction.SUBMIT, payload.note)


@router.post("/strategy-versions/{version_id}/approve", response_model=ApprovalResponse)
async def approve(
    version_id: UUID, payload: NoteRequest, tenant: ManageDep, session: SessionDep
) -> ApprovalResponse:
    return await _act(session, tenant, version_id, ApprovalAction.APPROVE, payload.note)


@router.post("/strategy-versions/{version_id}/reject", response_model=ApprovalResponse)
async def reject(
    version_id: UUID, payload: NoteRequest, tenant: ManageDep, session: SessionDep
) -> ApprovalResponse:
    return await _act(session, tenant, version_id, ApprovalAction.REJECT, payload.note)


@router.post("/strategy-versions/{version_id}/withdraw", response_model=ApprovalResponse)
async def withdraw(
    version_id: UUID, payload: NoteRequest, tenant: ManageDep, session: SessionDep
) -> ApprovalResponse:
    return await _act(session, tenant, version_id, ApprovalAction.WITHDRAW, payload.note)


@router.get("/strategy-versions/{version_id}/validate", response_model=list[str])
async def validate(version_id: UUID, tenant: ViewDep, session: SessionDep) -> list[str]:
    return await StrategyVersioningService(session).validate(tenant.organization_id, version_id)


@router.get("/strategy-versions/diff", response_model=dict[str, Any])
async def diff(
    tenant: ViewDep,
    session: SessionDep,
    from_version: Annotated[UUID, Query(alias="from")],
    to_version: Annotated[UUID, Query(alias="to")],
) -> dict[str, Any]:
    result = await StrategyVersioningService(session).diff(
        tenant.organization_id, from_version, to_version
    )
    data = asdict(result)
    data["has_changes"] = result.has_changes
    data["suggested_bump"] = result.suggested_bump()
    return data


@router.post("/strategies/{strategy_id}/deploy", status_code=201)
async def deploy(
    strategy_id: UUID, payload: DeployRequest, tenant: ManageDep, session: SessionDep
) -> dict[str, str]:
    await StrategyVersioningService(session).record_deployment(
        tenant.organization_id,
        version_id=payload.version_id,
        actor=tenant.user.user_id,
        action=payload.action,
    )
    return {"status": "recorded"}


@router.get("/strategies/{strategy_id}/deployments", response_model=list[dict[str, Any]])
async def deployment_history(
    strategy_id: UUID, tenant: ViewDep, session: SessionDep
) -> list[dict[str, Any]]:
    return await StrategyVersioningService(session).deployment_history(
        tenant.organization_id, strategy_id
    )
