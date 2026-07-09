"""In-app notifications plus live fan-out over Redis for WebSocket delivery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import and_, func, not_, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.notifications.domain.delivery import (
    Channel,
    DeliveryPreference,
    resolve_channels,
)
from algo_platform.modules.notifications.infrastructure.channels import (
    NotificationDispatcher,
    OutboundNotification,
)
from algo_platform.modules.notifications.infrastructure.models import (
    NotificationModel,
    NotificationReadModel,
)
from algo_platform.shared.domain.types import utc_now
from algo_platform.shared.infrastructure.redis_gateway import RedisGateway

Severity = Literal["info", "success", "warning", "critical"]

NOTIFICATIONS_CHANNEL = "notifications"


@dataclass(frozen=True, slots=True)
class ExternalDelivery:
    """Opt-in fan-out to external channels for a single ``notify`` call.

    Absent (the default), ``notify`` behaves exactly as before: in-app record
    plus Redis publish, no external side effects.
    """

    preference: DeliveryPreference
    dispatcher: NotificationDispatcher
    email_to: str | None = None
    webhook_url: str | None = None
    local_time: time | None = None


@dataclass(frozen=True, slots=True)
class NotificationDTO:
    id: UUID
    type: str
    severity: str
    title: str
    body: str
    payload: dict[str, Any]
    read: bool
    created_at: datetime


class NotificationService:
    def __init__(self, session: AsyncSession, redis: RedisGateway | None = None) -> None:
        self._session = session
        self._redis = redis

    async def notify(
        self,
        *,
        organization_id: UUID,
        title: str,
        body: str = "",
        type_: str = "general",
        severity: Severity = "info",
        user_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
        delivery: ExternalDelivery | None = None,
    ) -> UUID:
        model = NotificationModel(
            organization_id=organization_id,
            user_id=user_id,
            type=type_,
            severity=severity,
            title=title,
            body=body,
            payload=payload or {},
            created_at=utc_now(),
        )
        self._session.add(model)
        await self._session.flush()
        if self._redis is not None:
            await self._redis.publish_json(
                f"{NOTIFICATIONS_CHANNEL}:{organization_id}",
                {
                    "channel": "notifications",
                    "type": type_,
                    "severity": severity,
                    "title": title,
                    "body": body,
                    "notification_id": str(model.id),
                    "created_at": model.created_at.isoformat(),
                },
            )
        if delivery is not None:
            await self._dispatch_external(
                delivery,
                OutboundNotification(
                    type=type_,
                    severity=severity,
                    title=title,
                    body=body,
                    payload=payload or {},
                ),
            )
        return model.id

    @staticmethod
    async def _dispatch_external(
        delivery: ExternalDelivery, notification: OutboundNotification
    ) -> None:
        channels = resolve_channels(
            delivery.preference,
            type_=notification.type,
            severity=notification.severity,
            local_time=delivery.local_time,
        )
        if Channel.EMAIL in channels and delivery.email_to:
            await delivery.dispatcher.send_email(notification, to=delivery.email_to)
        if Channel.WEBHOOK in channels and delivery.webhook_url:
            await delivery.dispatcher.send_webhook(notification, url=delivery.webhook_url)

    async def list_for_user(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[NotificationDTO]:
        read_exists = (
            select(NotificationReadModel.id)
            .where(
                NotificationReadModel.notification_id == NotificationModel.id,
                NotificationReadModel.user_id == user_id,
            )
            .exists()
        )
        stmt = (
            select(NotificationModel, read_exists.label("broadcast_read"))
            .where(
                NotificationModel.organization_id == organization_id,
                or_(
                    NotificationModel.user_id.is_(None),
                    NotificationModel.user_id == user_id,
                ),
            )
            .order_by(NotificationModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if unread_only:
            stmt = stmt.where(
                or_(
                    and_(
                        NotificationModel.user_id.is_(None),
                        not_(read_exists),
                    ),
                    and_(
                        NotificationModel.user_id == user_id,
                        NotificationModel.read_at.is_(None),
                    ),
                )
            )
        rows = (await self._session.execute(stmt)).all()
        return [
            NotificationDTO(
                id=r.id,
                type=r.type,
                severity=r.severity,
                title=r.title,
                body=r.body,
                payload=dict(r.payload),
                read=(r.read_at is not None if r.user_id is not None else bool(broadcast_read)),
                created_at=r.created_at,
            )
            for r, broadcast_read in rows
        ]

    async def unread_count(self, *, organization_id: UUID, user_id: UUID) -> int:
        read_exists = (
            select(NotificationReadModel.id)
            .where(
                NotificationReadModel.notification_id == NotificationModel.id,
                NotificationReadModel.user_id == user_id,
            )
            .exists()
        )
        stmt = (
            select(func.count())
            .select_from(NotificationModel)
            .where(
                NotificationModel.organization_id == organization_id,
                or_(
                    NotificationModel.user_id.is_(None),
                    NotificationModel.user_id == user_id,
                ),
                or_(
                    and_(NotificationModel.user_id.is_(None), not_(read_exists)),
                    and_(
                        NotificationModel.user_id == user_id,
                        NotificationModel.read_at.is_(None),
                    ),
                ),
            )
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def mark_read(
        self, *, organization_id: UUID, user_id: UUID, notification_id: UUID
    ) -> None:
        notification = (
            await self._session.execute(
                select(NotificationModel).where(
                    NotificationModel.id == notification_id,
                    NotificationModel.organization_id == organization_id,
                    or_(
                        NotificationModel.user_id.is_(None),
                        NotificationModel.user_id == user_id,
                    ),
                )
            )
        ).scalar_one_or_none()
        if notification is None:
            return
        if notification.user_id is None:
            await self._session.execute(
                pg_insert(NotificationReadModel)
                .values(
                    notification_id=notification_id,
                    user_id=user_id,
                    read_at=utc_now(),
                )
                .on_conflict_do_nothing(
                    index_elements=["notification_id", "user_id"]
                )
            )
        else:
            notification.read_at = utc_now()

    async def mark_all_read(self, *, organization_id: UUID, user_id: UUID) -> None:
        broadcast_ids = (
            (
                await self._session.execute(
                    select(NotificationModel.id).where(
                        NotificationModel.organization_id == organization_id,
                        NotificationModel.user_id.is_(None),
                        not_(
                            select(NotificationReadModel.id)
                            .where(
                                NotificationReadModel.notification_id
                                == NotificationModel.id,
                                NotificationReadModel.user_id == user_id,
                            )
                            .exists()
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        now = utc_now()
        if broadcast_ids:
            await self._session.execute(
                pg_insert(NotificationReadModel)
                .values(
                    [
                        {
                            "notification_id": notification_id,
                            "user_id": user_id,
                            "read_at": now,
                        }
                        for notification_id in broadcast_ids
                    ]
                )
                .on_conflict_do_nothing(
                    index_elements=["notification_id", "user_id"]
                )
            )
        await self._session.execute(
            update(NotificationModel)
            .where(
                NotificationModel.organization_id == organization_id,
                NotificationModel.user_id == user_id,
                NotificationModel.read_at.is_(None),
            )
            .values(read_at=now)
        )
