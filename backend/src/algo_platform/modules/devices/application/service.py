"""Trading devices: keys, ingestion, status.

A device authenticates with one long random key (shown once, stored hashed)
and posts events to a single endpoint. Heartbeats update the device row in
place; trades, logs and alerts are appended as events; the latest positions
list replaces the previous one. Alerts and error logs raise an in-app
notification for the organization.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.devices.domain.events import DeviceEvent
from algo_platform.modules.devices.infrastructure.models import DeviceEventModel, DeviceModel
from algo_platform.modules.notifications.application.service import NotificationService
from algo_platform.shared.domain.errors import AuthenticationFailed, NotFoundError
from algo_platform.shared.domain.types import utc_now
from algo_platform.shared.infrastructure.security import generate_opaque_token, hash_token

logger = structlog.get_logger(__name__)

KEY_PREFIX = "amd"
# A device is "online" if it sent anything within this window.
ONLINE_WINDOW = timedelta(minutes=3)
EVENT_RETENTION = timedelta(days=30)
MAX_NOTIFICATIONS_PER_REQUEST = 5


@dataclass(frozen=True, slots=True)
class DeviceDTO:
    id: UUID
    name: str
    kind: str
    key_prefix: str
    status: str  # online | offline | never_seen | revoked
    created_at: datetime
    revoked_at: datetime | None
    last_seen_at: datetime | None
    last_heartbeat_at: datetime | None
    last_ip: str | None
    health: dict[str, Any] | None
    positions: list[Any] | None
    positions_at: datetime | None


@dataclass(frozen=True, slots=True)
class DeviceEventDTO:
    id: UUID
    kind: str
    severity: str
    message: str
    payload: dict[str, Any]
    occurred_at: datetime
    received_at: datetime


def device_status(model: DeviceModel, now: datetime) -> str:
    if model.revoked_at is not None:
        return "revoked"
    if model.last_seen_at is None:
        return "never_seen"
    return "online" if now - model.last_seen_at <= ONLINE_WINDOW else "offline"


def _dto(model: DeviceModel, now: datetime) -> DeviceDTO:
    return DeviceDTO(
        id=model.id,
        name=model.name,
        kind=model.kind,
        key_prefix=model.key_prefix,
        status=device_status(model, now),
        created_at=model.created_at,
        revoked_at=model.revoked_at,
        last_seen_at=model.last_seen_at,
        last_heartbeat_at=model.last_heartbeat_at,
        last_ip=model.last_ip,
        health=model.health,
        positions=model.positions,
        positions_at=model.positions_at,
    )


def _prefix_of(raw_key: str) -> str | None:
    parts = raw_key.split("_", 2)
    if len(parts) != 3 or parts[0] != KEY_PREFIX or not parts[1]:
        return None
    return parts[1]


class DeviceService:
    def __init__(self, session: AsyncSession, notifications: NotificationService | None = None):
        self._session = session
        self._notifications = notifications

    # -- management ----------------------------------------------------------------

    async def create(
        self, organization_id: UUID, *, name: str, kind: str, created_by: UUID
    ) -> tuple[DeviceDTO, str]:
        prefix = generate_opaque_token(6).replace("_", "x").replace("-", "y")[:8]
        raw_key = f"{KEY_PREFIX}_{prefix}_{generate_opaque_token(32)}"
        model = DeviceModel(
            organization_id=organization_id,
            name=name.strip(),
            kind=kind,
            key_prefix=prefix,
            key_hash=hash_token(raw_key),
            created_by=created_by,
            created_at=utc_now(),
        )
        self._session.add(model)
        await self._session.flush()
        return _dto(model, utc_now()), raw_key

    async def list_devices(self, organization_id: UUID) -> list[DeviceDTO]:
        rows = (
            await self._session.execute(
                select(DeviceModel)
                .where(DeviceModel.organization_id == organization_id)
                .order_by(DeviceModel.revoked_at.is_not(None), DeviceModel.created_at.desc())
            )
        ).scalars()
        now = utc_now()
        return [_dto(row, now) for row in rows]

    async def _owned(self, organization_id: UUID, device_id: UUID) -> DeviceModel:
        model = await self._session.get(DeviceModel, device_id)
        if model is None or model.organization_id != organization_id:
            raise NotFoundError("device not found")
        return model

    async def revoke(self, organization_id: UUID, device_id: UUID) -> DeviceDTO:
        model = await self._owned(organization_id, device_id)
        if model.revoked_at is None:
            model.revoked_at = utc_now()
            await self._session.flush()
        return _dto(model, utc_now())

    async def events(
        self, organization_id: UUID, device_id: UUID, *, kind: str | None, limit: int
    ) -> list[DeviceEventDTO]:
        await self._owned(organization_id, device_id)
        stmt = select(DeviceEventModel).where(DeviceEventModel.device_id == device_id)
        if kind:
            stmt = stmt.where(DeviceEventModel.kind == kind)
        rows = (
            await self._session.execute(
                stmt.order_by(DeviceEventModel.occurred_at.desc()).limit(limit)
            )
        ).scalars()
        return [
            DeviceEventDTO(
                id=row.id,
                kind=row.kind,
                severity=row.severity,
                message=row.message,
                payload=row.payload,
                occurred_at=row.occurred_at,
                received_at=row.received_at,
            )
            for row in rows
        ]

    # -- ingestion -------------------------------------------------------------------

    async def authenticate(self, raw_key: str | None) -> DeviceModel:
        if not raw_key or _prefix_of(raw_key.strip()) is None:
            raise AuthenticationFailed("a valid X-Device-Key header is required")
        model = (
            await self._session.execute(
                select(DeviceModel).where(DeviceModel.key_hash == hash_token(raw_key.strip()))
            )
        ).scalar_one_or_none()
        if model is None or model.revoked_at is not None:
            raise AuthenticationFailed("device key is invalid or revoked")
        return model

    async def ingest(
        self, device: DeviceModel, events: list[DeviceEvent], *, ip: str | None
    ) -> dict[str, int]:
        now = utc_now()
        device.last_seen_at = now
        device.last_ip = ip
        counts: dict[str, int] = {}
        notified = 0
        for event in events:
            counts[event.kind] = counts.get(event.kind, 0) + 1
            if event.kind == "heartbeat":
                if (
                    device.last_heartbeat_at is None
                    or event.occurred_at >= device.last_heartbeat_at
                ):
                    device.last_heartbeat_at = event.occurred_at
                    device.health = event.payload
                continue
            if event.kind == "positions" and (
                device.positions_at is None or event.occurred_at >= device.positions_at
            ):
                device.positions = event.payload["positions"]
                device.positions_at = event.occurred_at
            self._session.add(
                DeviceEventModel(
                    device_id=device.id,
                    organization_id=device.organization_id,
                    kind=event.kind,
                    severity=event.severity,
                    message=event.message,
                    payload=event.payload,
                    occurred_at=event.occurred_at,
                    received_at=now,
                )
            )
            if (
                event.is_notable
                and self._notifications is not None
                and notified < MAX_NOTIFICATIONS_PER_REQUEST
            ):
                notified += 1
                await self._notifications.notify(
                    organization_id=device.organization_id,
                    title=f"{device.name}: {event.message[:120]}",
                    body=f"{event.kind} · {event.severity} · {event.occurred_at.isoformat()}",
                    type_="device",
                    severity="critical" if event.severity in ("critical", "error") else "warning",
                    payload={"device_id": str(device.id)},
                )
        await self._session.flush()
        return counts

    async def prune(self) -> int:
        """Drop events older than the retention window (scheduler job)."""
        result = await self._session.execute(
            delete(DeviceEventModel).where(
                DeviceEventModel.received_at < utc_now() - EVENT_RETENTION
            )
        )
        return int(getattr(result, "rowcount", 0) or 0)
