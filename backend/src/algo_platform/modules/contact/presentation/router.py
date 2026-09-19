from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from algo_platform.api.dependencies.auth import PlatformAdminDep
from algo_platform.api.dependencies.core import SessionDep, SettingsDep
from algo_platform.api.dependencies.rate_limit import rate_limit
from algo_platform.modules.contact.application.service import ContactService
from algo_platform.shared.infrastructure.email_outbox import TransactionalEmailSender

router = APIRouter(tags=["contact"])


class ContactRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    topic: Literal["access", "support", "partnership", "other"] = "other"
    message: str = Field(min_length=10, max_length=5000)
    # Honeypot: hidden from people, filled in by naive bots. Never shown or stored.
    website: str | None = Field(default=None, max_length=200)


class MessageResponse(BaseModel):
    message: str


class ContactMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


def _service(session: SessionDep, settings: SettingsDep) -> ContactService:
    return ContactService(
        session=session,
        email_sender=TransactionalEmailSender(session),
        app_base_url=settings.app_base_url,
    )


ContactServiceDep = Annotated[ContactService, Depends(_service)]

_RECEIVED = "thanks, your message was received. We usually reply within one working day"


@router.post(
    "/contact",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("contact", times=3, seconds=600))],
)
async def contact(payload: ContactRequest, service: ContactServiceDep) -> MessageResponse:
    """Public: anyone may write in, signed in or not."""
    if payload.website:
        # Same answer as a real submission so bots learn nothing.
        return MessageResponse(message=_RECEIVED)
    await service.submit(
        name=payload.name, email=payload.email, topic=payload.topic, message=payload.message
    )
    return MessageResponse(message=_RECEIVED)


@router.get("/admin/contact-messages", response_model=list[ContactMessageResponse])
async def list_messages(
    admin: PlatformAdminDep,
    service: ContactServiceDep,
    status_filter: Annotated[Literal["open", "resolved"] | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[ContactMessageResponse]:
    messages = await service.list_messages(status=status_filter, limit=limit)
    return [ContactMessageResponse.model_validate(m) for m in messages]


@router.post("/admin/contact-messages/{message_id}/resolve", response_model=ContactMessageResponse)
async def resolve_message(
    message_id: UUID, admin: PlatformAdminDep, service: ContactServiceDep
) -> ContactMessageResponse:
    return ContactMessageResponse.model_validate(
        await service.resolve(message_id, resolved_by=admin.user_id)
    )
