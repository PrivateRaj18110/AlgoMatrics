from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict

from algo_platform.api.dependencies.core import RedisDep, SessionDep
from algo_platform.api.dependencies.pagination import PageDep
from algo_platform.api.dependencies.tenant import TenantDep
from algo_platform.modules.notifications.application.service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


def get_notification_service(session: SessionDep, redis: RedisDep) -> NotificationService:
    return NotificationService(session, redis)


ServiceDep = Annotated[NotificationService, Depends(get_notification_service)]


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    type: str
    severity: str
    title: str
    body: str
    payload: dict[str, Any]
    read: bool
    created_at: datetime


class UnreadCountResponse(BaseModel):
    count: int


class MessageResponse(BaseModel):
    message: str


@router.get("", response_model=list[NotificationResponse])
async def list_notifications(
    tenant: TenantDep,
    service: ServiceDep,
    page: PageDep,
    unread_only: Annotated[bool, Query()] = False,
) -> list[NotificationResponse]:
    items = await service.list_for_user(
        organization_id=tenant.organization_id,
        user_id=tenant.user.user_id,
        unread_only=unread_only,
        limit=page.limit,
        offset=page.offset,
    )
    return [NotificationResponse.model_validate(n) for n in items]


@router.get("/unread-count", response_model=UnreadCountResponse)
async def unread_count(tenant: TenantDep, service: ServiceDep) -> UnreadCountResponse:
    count = await service.unread_count(
        organization_id=tenant.organization_id, user_id=tenant.user.user_id
    )
    return UnreadCountResponse(count=count)


@router.post("/{notification_id}/read", response_model=MessageResponse)
async def mark_read(
    notification_id: UUID, tenant: TenantDep, service: ServiceDep
) -> MessageResponse:
    await service.mark_read(
        organization_id=tenant.organization_id,
        user_id=tenant.user.user_id,
        notification_id=notification_id,
    )
    return MessageResponse(message="marked as read")


@router.post("/read-all", response_model=MessageResponse)
async def mark_all_read(tenant: TenantDep, service: ServiceDep) -> MessageResponse:
    await service.mark_all_read(organization_id=tenant.organization_id, user_id=tenant.user.user_id)
    return MessageResponse(message="all notifications marked as read")
