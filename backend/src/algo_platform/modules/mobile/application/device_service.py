"""Register, list, and prune mobile devices; fan a push out to a user."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.mobile.application.ports import (
    PushProvider,
    PushTarget,
)
from algo_platform.modules.mobile.domain.devices import (
    PushMessage,
    normalize_push_token,
    parse_platform,
)
from algo_platform.modules.mobile.infrastructure.models import MobileDeviceModel
from algo_platform.shared.domain.errors import NotFoundError
from algo_platform.shared.domain.types import TenantId, UserId, utc_now


@dataclass(frozen=True, slots=True)
class DeviceDTO:
    id: UUID
    platform: str
    app_version: str | None
    device_name: str | None
    created_at: datetime
    last_seen_at: datetime


def _to_dto(model: MobileDeviceModel) -> DeviceDTO:
    return DeviceDTO(
        id=model.id,
        platform=model.platform,
        app_version=model.app_version,
        device_name=model.device_name,
        created_at=model.created_at,
        last_seen_at=model.last_seen_at,
    )


class DeviceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def register(
        self,
        organization_id: TenantId,
        user_id: UserId,
        *,
        platform: str,
        push_token: str,
        app_version: str | None = None,
        device_name: str | None = None,
    ) -> DeviceDTO:
        token = normalize_push_token(push_token)
        parsed = parse_platform(platform)
        now = utc_now()
        existing = (
            await self._session.execute(
                select(MobileDeviceModel).where(MobileDeviceModel.push_token == token)
            )
        ).scalar_one_or_none()
        if existing is not None:
            # Same physical device install: re-home it to the current user/org.
            existing.organization_id = organization_id
            existing.user_id = user_id
            existing.platform = parsed.value
            existing.app_version = app_version
            existing.device_name = device_name
            existing.last_seen_at = now
            await self._session.flush()
            return _to_dto(existing)
        model = MobileDeviceModel(
            organization_id=organization_id,
            user_id=user_id,
            platform=parsed.value,
            push_token=token,
            app_version=app_version,
            device_name=device_name,
            created_at=now,
            last_seen_at=now,
        )
        self._session.add(model)
        await self._session.flush()
        return _to_dto(model)

    async def list_for_user(
        self, organization_id: TenantId, user_id: UserId
    ) -> list[DeviceDTO]:
        rows = (
            (
                await self._session.execute(
                    select(MobileDeviceModel)
                    .where(
                        MobileDeviceModel.organization_id == organization_id,
                        MobileDeviceModel.user_id == user_id,
                    )
                    .order_by(MobileDeviceModel.last_seen_at.desc())
                )
            )
            .scalars()
            .all()
        )
        return [_to_dto(r) for r in rows]

    async def unregister(
        self, organization_id: TenantId, user_id: UserId, device_id: UUID
    ) -> None:
        model = await self._session.get(MobileDeviceModel, device_id)
        if (
            model is None
            or model.organization_id != organization_id
            or model.user_id != user_id
        ):
            raise NotFoundError("device not found")
        await self._session.delete(model)
        await self._session.flush()

    async def push_to_user(
        self,
        organization_id: TenantId,
        user_id: UserId,
        message: PushMessage,
        *,
        provider: PushProvider,
    ) -> int:
        """Deliver a push to every registered device of a user.

        Tokens the provider reports invalid are pruned so a stale install stops
        receiving. Returns the number of successful deliveries.
        """

        rows = (
            (
                await self._session.execute(
                    select(MobileDeviceModel).where(
                        MobileDeviceModel.organization_id == organization_id,
                        MobileDeviceModel.user_id == user_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            return 0
        targets = [
            PushTarget(token=r.push_token, platform=parse_platform(r.platform)) for r in rows
        ]
        result = await provider.send(message.truncated(), targets)
        if result.invalid_tokens:
            await self._session.execute(
                delete(MobileDeviceModel).where(
                    MobileDeviceModel.push_token.in_(result.invalid_tokens)
                )
            )
            await self._session.flush()
        return result.delivered
