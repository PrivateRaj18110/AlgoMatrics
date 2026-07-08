"""Audit trail: immutable actor/action evidence with request correlation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.audit.infrastructure.models import AuditLogModel
from algo_platform.shared.domain.types import utc_now


@dataclass(frozen=True, slots=True)
class AuditEntryDTO:
    id: UUID
    organization_id: UUID | None
    actor_user_id: UUID | None
    actor_type: str
    action: str
    resource_type: str
    resource_id: str
    request_id: str | None
    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None
    occurred_at: datetime


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str = "",
        organization_id: UUID | None = None,
        actor_user_id: UUID | None = None,
        actor_type: str = "user",
        request_id: str | None = None,
        ip_hash: str | None = None,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
    ) -> None:
        self._session.add(
            AuditLogModel(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                actor_type=actor_type,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                request_id=request_id,
                ip_hash=ip_hash,
                before_state=before_state,
                after_state=after_state,
                occurred_at=utc_now(),
            )
        )

    async def search(
        self,
        *,
        organization_id: UUID | None,
        action_prefix: str | None = None,
        actor_user_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AuditEntryDTO], int]:
        stmt = select(AuditLogModel)
        count_stmt = select(func.count()).select_from(AuditLogModel)
        if organization_id is not None:
            stmt = stmt.where(AuditLogModel.organization_id == organization_id)
            count_stmt = count_stmt.where(AuditLogModel.organization_id == organization_id)
        if action_prefix:
            stmt = stmt.where(AuditLogModel.action.startswith(action_prefix))
            count_stmt = count_stmt.where(AuditLogModel.action.startswith(action_prefix))
        if actor_user_id is not None:
            stmt = stmt.where(AuditLogModel.actor_user_id == actor_user_id)
            count_stmt = count_stmt.where(AuditLogModel.actor_user_id == actor_user_id)
        stmt = stmt.order_by(AuditLogModel.occurred_at.desc()).limit(limit).offset(offset)
        rows = (await self._session.execute(stmt)).scalars().all()
        total = int((await self._session.execute(count_stmt)).scalar_one())
        return (
            [
                AuditEntryDTO(
                    id=r.id,
                    organization_id=r.organization_id,
                    actor_user_id=r.actor_user_id,
                    actor_type=r.actor_type,
                    action=r.action,
                    resource_type=r.resource_type,
                    resource_id=r.resource_id,
                    request_id=r.request_id,
                    before_state=r.before_state,
                    after_state=r.after_state,
                    occurred_at=r.occurred_at,
                )
                for r in rows
            ],
            total,
        )
