"""Public contact form: store the message, tell the platform owner."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.contact.infrastructure.models import ContactMessageModel
from algo_platform.modules.identity.application.directory import UserDirectory
from algo_platform.shared.application.ports import EmailMessage, EmailSender
from algo_platform.shared.domain.errors import ConflictError, NotFoundError
from algo_platform.shared.domain.types import utc_now
from algo_platform.shared.infrastructure.client_context import current_client
from algo_platform.shared.infrastructure.geoip import geoip

logger = structlog.get_logger(__name__)

TOPICS = ("access", "support", "partnership", "other")


@dataclass(frozen=True, slots=True)
class ContactMessageDTO:
    id: UUID
    name: str
    email: str
    topic: str
    message: str
    status: str
    ip_address: str | None
    geo: dict[str, Any] | None
    created_at: datetime
    resolved_at: datetime | None


def _dto(model: ContactMessageModel) -> ContactMessageDTO:
    return ContactMessageDTO(
        id=model.id,
        name=model.name,
        email=model.email,
        topic=model.topic,
        message=model.message,
        status=model.status,
        ip_address=model.ip_address,
        geo=model.geo,
        created_at=model.created_at,
        resolved_at=model.resolved_at,
    )


class ContactService:
    def __init__(
        self, *, session: AsyncSession, email_sender: EmailSender, app_base_url: str
    ) -> None:
        self._session = session
        self._email_sender = email_sender
        self._app_base_url = app_base_url

    async def submit(self, *, name: str, email: str, topic: str, message: str) -> None:
        client = current_client()
        ip = client.ip_address if client else None
        location = geoip().lookup(ip)
        model = ContactMessageModel(
            name=name.strip(),
            email=email.strip().lower(),
            topic=topic if topic in TOPICS else "other",
            message=message.strip(),
            ip_address=ip,
            user_agent=client.user_agent if client else None,
            geo=location.as_dict() if location else None,
            created_at=utc_now(),
        )
        self._session.add(model)
        await self._session.flush()

        admins = await UserDirectory(self._session).platform_admin_emails()
        inbox = f"{self._app_base_url}/app/admin/messages"
        for admin_email in admins:
            await self._email_sender.send(
                EmailMessage(
                    to=admin_email,
                    subject=f"[Contact · {model.topic}] {model.name}",
                    text=(
                        f"From: {model.name} <{model.email}>\n"
                        f"Topic: {model.topic}\n\n{model.message}\n\n"
                        f"Reply directly to {model.email}, or see all messages: {inbox}"
                    ),
                )
            )
        logger.info("contact.message_received", message_id=str(model.id), topic=model.topic)

    async def list_messages(self, *, status: str | None, limit: int) -> list[ContactMessageDTO]:
        stmt = select(ContactMessageModel).order_by(ContactMessageModel.created_at.desc())
        if status:
            stmt = stmt.where(ContactMessageModel.status == status)
        rows = (await self._session.execute(stmt.limit(limit))).scalars().all()
        return [_dto(row) for row in rows]

    async def open_count(self) -> int:
        return int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(ContactMessageModel)
                    .where(ContactMessageModel.status == "open")
                )
            ).scalar_one()
        )

    async def resolve(self, message_id: UUID, *, resolved_by: UUID) -> ContactMessageDTO:
        model = await self._session.get(ContactMessageModel, message_id)
        if model is None:
            raise NotFoundError("message not found")
        if model.status == "resolved":
            raise ConflictError("message is already resolved")
        model.status = "resolved"
        model.resolved_at = utc_now()
        model.resolved_by = resolved_by
        await self._session.flush()
        return _dto(model)
