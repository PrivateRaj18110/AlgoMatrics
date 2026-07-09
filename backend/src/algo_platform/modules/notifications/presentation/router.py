from __future__ import annotations

from datetime import datetime, time
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from algo_platform.api.dependencies.core import RedisDep, SessionDep
from algo_platform.api.dependencies.pagination import PageDep
from algo_platform.api.dependencies.tenant import TenantDep
from algo_platform.modules.notifications.application.preferences import (
    NotificationPreferenceService,
    PreferenceDTO,
)
from algo_platform.modules.notifications.application.service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


def get_notification_service(session: SessionDep, redis: RedisDep) -> NotificationService:
    return NotificationService(session, redis)


ServiceDep = Annotated[NotificationService, Depends(get_notification_service)]


def get_preference_service(session: SessionDep) -> NotificationPreferenceService:
    return NotificationPreferenceService(session)


PreferenceServiceDep = Annotated[
    NotificationPreferenceService, Depends(get_preference_service)
]


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


_CHANNELS = {"in_app", "email", "webhook"}
_SEVERITIES = {"info", "success", "warning", "critical"}


class PreferenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    enabled_channels: list[str]
    muted_types: list[str]
    min_severity: str
    quiet_start: time | None
    quiet_end: time | None
    critical_overrides_quiet: bool
    webhook_url: str | None


class PreferenceUpdate(BaseModel):
    enabled_channels: list[str] = Field(default_factory=lambda: ["in_app"])
    muted_types: list[str] = Field(default_factory=list)
    min_severity: str = Field(default="info")
    quiet_start: time | None = None
    quiet_end: time | None = None
    critical_overrides_quiet: bool = True
    webhook_url: str | None = Field(default=None, max_length=500)


def _to_response(dto: PreferenceDTO) -> PreferenceResponse:
    return PreferenceResponse.model_validate(dto)


@router.get("/preferences", response_model=PreferenceResponse)
async def get_preferences(
    tenant: TenantDep, service: PreferenceServiceDep
) -> PreferenceResponse:
    dto = await service.get(tenant.organization_id, tenant.user.user_id)
    return _to_response(dto)


@router.put("/preferences", response_model=PreferenceResponse)
async def update_preferences(
    payload: PreferenceUpdate, tenant: TenantDep, service: PreferenceServiceDep
) -> PreferenceResponse:
    channels = [c for c in payload.enabled_channels if c in _CHANNELS] or ["in_app"]
    severity = payload.min_severity if payload.min_severity in _SEVERITIES else "info"
    dto = await service.update(
        tenant.organization_id,
        tenant.user.user_id,
        enabled_channels=channels,
        muted_types=payload.muted_types,
        min_severity=severity,
        quiet_start=payload.quiet_start,
        quiet_end=payload.quiet_end,
        critical_overrides_quiet=payload.critical_overrides_quiet,
        webhook_url=payload.webhook_url,
    )
    return _to_response(dto)
