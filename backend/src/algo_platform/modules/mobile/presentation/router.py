"""Mobile backend HTTP surface: device registry + a bootstrap aggregate.

The bootstrap endpoint collapses a mobile cold-start (profile, unread badge,
enabled features, device count) into one round-trip.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from algo_platform.api.dependencies.core import RedisDep, SessionDep, SettingsDep
from algo_platform.api.dependencies.tenant import TenantDep
from algo_platform.modules.feature_flags.application.service import FeatureFlagService
from algo_platform.modules.feature_flags.domain.flags import EvaluationContext
from algo_platform.modules.mobile.application.device_service import DeviceService
from algo_platform.modules.notifications.application.service import NotificationService

router = APIRouter(prefix="/mobile", tags=["mobile"])


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    platform: str
    app_version: str | None
    device_name: str | None
    created_at: datetime
    last_seen_at: datetime


class DeviceRegistration(BaseModel):
    platform: str = Field(pattern="^(ios|android|web)$")
    push_token: str = Field(min_length=1, max_length=4096)
    app_version: str | None = Field(default=None, max_length=40)
    device_name: str | None = Field(default=None, max_length=120)


class MessageResponse(BaseModel):
    message: str


class BootstrapUser(BaseModel):
    user_id: UUID
    email: str
    organization_id: UUID
    role: str


class BootstrapResponse(BaseModel):
    user: BootstrapUser
    unread_notifications: int
    device_count: int
    features: dict[str, bool]


@router.post("/devices", response_model=DeviceResponse, status_code=201)
async def register_device(
    payload: DeviceRegistration, tenant: TenantDep, session: SessionDep
) -> DeviceResponse:
    dto = await DeviceService(session).register(
        tenant.organization_id,
        tenant.user.user_id,
        platform=payload.platform,
        push_token=payload.push_token,
        app_version=payload.app_version,
        device_name=payload.device_name,
    )
    return DeviceResponse.model_validate(dto)


@router.get("/devices", response_model=list[DeviceResponse])
async def list_devices(tenant: TenantDep, session: SessionDep) -> list[DeviceResponse]:
    devices = await DeviceService(session).list_for_user(
        tenant.organization_id, tenant.user.user_id
    )
    return [DeviceResponse.model_validate(d) for d in devices]


@router.delete("/devices/{device_id}", response_model=MessageResponse)
async def unregister_device(
    device_id: UUID, tenant: TenantDep, session: SessionDep
) -> MessageResponse:
    await DeviceService(session).unregister(
        tenant.organization_id, tenant.user.user_id, device_id
    )
    return MessageResponse(message="device unregistered")


@router.get("/bootstrap", response_model=BootstrapResponse)
async def bootstrap(
    tenant: TenantDep, session: SessionDep, redis: RedisDep, settings: SettingsDep
) -> BootstrapResponse:
    notifications = NotificationService(session, redis)
    unread = await notifications.unread_count(
        organization_id=tenant.organization_id, user_id=tenant.user.user_id
    )
    devices = await DeviceService(session).list_for_user(
        tenant.organization_id, tenant.user.user_id
    )
    features = await FeatureFlagService(session, redis).evaluate_all(
        EvaluationContext(
            environment=settings.app_env,
            organization_id=tenant.organization_id,
            user_id=tenant.user.user_id,
        )
    )
    return BootstrapResponse(
        user=BootstrapUser(
            user_id=tenant.user.user_id,
            email=tenant.user.email,
            organization_id=tenant.organization_id,
            role=tenant.role.value,
        ),
        unread_notifications=unread,
        device_count=len(devices),
        features=features,
    )
