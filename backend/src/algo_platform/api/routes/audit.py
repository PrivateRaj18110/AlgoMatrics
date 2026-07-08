"""Organization-scoped audit trail access."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict

from algo_platform.api.dependencies.core import SessionDep
from algo_platform.api.dependencies.pagination import PageDep
from algo_platform.api.dependencies.tenant import TenantContext, require_permission
from algo_platform.modules.audit.application.service import AuditService
from algo_platform.modules.organizations.domain.roles import Permission

router = APIRouter(tags=["audit"])

AuditViewTenant = Annotated[TenantContext, Depends(require_permission(Permission.AUDIT_VIEW))]


class AuditEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor_user_id: UUID | None
    actor_type: str
    action: str
    resource_type: str
    resource_id: str
    request_id: str | None
    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None
    occurred_at: datetime


class PagedAuditResponse(BaseModel):
    items: list[AuditEntryResponse]
    total: int


@router.get("/audit-events", response_model=PagedAuditResponse)
async def list_audit_events(
    tenant: AuditViewTenant,
    session: SessionDep,
    page: PageDep,
    action_prefix: Annotated[str | None, Query(max_length=60)] = None,
    actor_user_id: Annotated[UUID | None, Query()] = None,
) -> PagedAuditResponse:
    entries, total = await AuditService(session).search(
        organization_id=tenant.organization_id,
        action_prefix=action_prefix,
        actor_user_id=actor_user_id,
        limit=page.limit,
        offset=page.offset,
    )
    return PagedAuditResponse(
        items=[AuditEntryResponse.model_validate(e) for e in entries], total=total
    )
