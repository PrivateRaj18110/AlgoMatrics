from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from algo_platform.api.dependencies.core import RedisDep, SessionDep
from algo_platform.api.dependencies.tenant import TenantContext, require_permission
from algo_platform.modules.audit.application.service import AuditService
from algo_platform.modules.devices.application.service import DeviceService
from algo_platform.modules.devices.domain.events import parse_events
from algo_platform.modules.notifications.application.service import NotificationService
from algo_platform.modules.organizations.domain.roles import Permission
from algo_platform.shared.domain.errors import RateLimited, ValidationFailed
from algo_platform.shared.domain.types import utc_now

router = APIRouter(tags=["devices"])

ViewTenant = Annotated[TenantContext, Depends(require_permission(Permission.ORG_VIEW))]
ManageTenant = Annotated[TenantContext, Depends(require_permission(Permission.ORG_MANAGE))]

MAX_BODY_BYTES = 512 * 1024
REQUESTS_PER_MINUTE = 120


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    kind: str
    key_prefix: str
    status: str
    created_at: datetime
    revoked_at: datetime | None
    last_seen_at: datetime | None
    last_heartbeat_at: datetime | None
    last_ip: str | None
    health: dict[str, Any] | None
    positions: list[Any] | None
    positions_at: datetime | None


class CreatedDeviceResponse(BaseModel):
    device: DeviceResponse
    key: str = Field(description="Shown once. Store it on the device; it cannot be retrieved.")
    ingest_url: str


class CreateDeviceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["trading", "vps", "mt5", "desktop", "other"] = "trading"


class DeviceEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    severity: str
    message: str
    payload: dict[str, Any]
    occurred_at: datetime
    received_at: datetime


class IngestResponse(BaseModel):
    accepted: int
    by_type: dict[str, int]
    rejected: list[dict[str, Any]]


# -- device-facing -------------------------------------------------------------------


@router.post("/ingest", response_model=IngestResponse)
async def ingest(request: Request, session: SessionDep, redis: RedisDep) -> IngestResponse:
    """The one endpoint a trading device talks to. Auth: ``X-Device-Key``.

    Body: one event, a list, or ``{"events": [...]}``. See docs/operations/device-ingest.md.
    """
    service = DeviceService(session, NotificationService(session, redis))
    device = await service.authenticate(request.headers.get("X-Device-Key"))
    window = int(time.time() // 60)
    if await redis.incr_fixed_window(f"ingest:{device.id}:{window}", 60) > REQUESTS_PER_MINUTE:
        raise RateLimited(
            f"at most {REQUESTS_PER_MINUTE} requests per minute per device; batch your events",
            retry_after_seconds=60,
        )
    declared = request.headers.get("Content-Length", "")
    if declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise ValidationFailed(
            f"body larger than {MAX_BODY_BYTES // 1024} KB; send smaller batches"
        )
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise ValidationFailed(
            f"body larger than {MAX_BODY_BYTES // 1024} KB; send smaller batches"
        )
    try:
        body = json.loads(raw or b"null")
    except ValueError as error:
        raise ValidationFailed("body must be JSON") from error
    parsed = parse_events(body, now=utc_now())
    counts = await service.ingest(
        device, parsed.accepted, ip=request.client.host if request.client else None
    )
    return IngestResponse(accepted=len(parsed.accepted), by_type=counts, rejected=parsed.rejected)


# -- organization-facing -------------------------------------------------------------------


@router.get("/devices", response_model=list[DeviceResponse])
async def list_devices(tenant: ViewTenant, session: SessionDep) -> list[DeviceResponse]:
    devices = await DeviceService(session).list_devices(tenant.organization_id)
    return [DeviceResponse.model_validate(d) for d in devices]


@router.post("/devices", response_model=CreatedDeviceResponse, status_code=status.HTTP_201_CREATED)
async def create_device(
    payload: CreateDeviceRequest, request: Request, tenant: ManageTenant, session: SessionDep
) -> CreatedDeviceResponse:
    device, key = await DeviceService(session).create(
        tenant.organization_id, name=payload.name, kind=payload.kind, created_by=tenant.user.user_id
    )
    await AuditService(session).record(
        action="devices.created",
        resource_type="device",
        resource_id=str(device.id),
        organization_id=tenant.organization_id,
        actor_user_id=tenant.user.user_id,
        request_id=getattr(request.state, "request_id", None),
        after_state={"name": device.name, "kind": device.kind, "key_prefix": device.key_prefix},
    )
    base = str(request.base_url).rstrip("/")
    return CreatedDeviceResponse(
        device=DeviceResponse.model_validate(device), key=key, ingest_url=f"{base}/api/v1/ingest"
    )


@router.delete("/devices/{device_id}", response_model=DeviceResponse)
async def revoke_device(
    device_id: UUID, request: Request, tenant: ManageTenant, session: SessionDep
) -> DeviceResponse:
    device = await DeviceService(session).revoke(tenant.organization_id, device_id)
    await AuditService(session).record(
        action="devices.revoked",
        resource_type="device",
        resource_id=str(device_id),
        organization_id=tenant.organization_id,
        actor_user_id=tenant.user.user_id,
        request_id=getattr(request.state, "request_id", None),
    )
    return DeviceResponse.model_validate(device)


@router.get("/devices/{device_id}/events", response_model=list[DeviceEventResponse])
async def device_events(
    device_id: UUID,
    tenant: ViewTenant,
    session: SessionDep,
    kind: Annotated[Literal["trade", "positions", "log", "alert"] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[DeviceEventResponse]:
    events = await DeviceService(session).events(
        tenant.organization_id, device_id, kind=kind, limit=limit
    )
    return [DeviceEventResponse.model_validate(e) for e in events]
