from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.workspace.infrastructure.models import WorkspaceTaskModel
from algo_platform.shared.domain.errors import NotFoundError, ValidationFailed
from algo_platform.shared.domain.types import TenantId, UserId, utc_now

_ALLOWED_PRIORITIES = frozenset({"low", "normal", "high"})


@dataclass(frozen=True, slots=True)
class TaskDTO:
    id: UUID
    title: str
    notes: str | None
    priority: str
    due_at: datetime | None
    completed_at: datetime | None
    archived_at: datetime | None
    tag: str | None
    created_at: datetime
    updated_at: datetime


def _dto(row: WorkspaceTaskModel) -> TaskDTO:
    return TaskDTO(
        id=row.id,
        title=row.title,
        notes=row.notes,
        priority=row.priority,
        due_at=row.due_at,
        completed_at=row.completed_at,
        archived_at=row.archived_at,
        tag=row.tag,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class WorkspaceTaskService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(self, organization_id: TenantId, user_id: UserId) -> list[TaskDTO]:
        rows = (
            await self._session.execute(
                select(WorkspaceTaskModel)
                .where(
                    WorkspaceTaskModel.organization_id == organization_id,
                    WorkspaceTaskModel.user_id == user_id,
                    WorkspaceTaskModel.archived_at.is_(None),
                )
                .order_by(WorkspaceTaskModel.created_at.desc())
            )
        ).scalars().all()
        return [_dto(row) for row in rows]

    async def create(
        self,
        organization_id: TenantId,
        user_id: UserId,
        *,
        title: str,
        priority: str = "normal",
        due_at: datetime | None = None,
        tag: str | None = None,
        notes: str | None = None,
    ) -> TaskDTO:
        cleaned = title.strip()
        if not cleaned:
            raise ValidationFailed("title is required")
        if priority not in _ALLOWED_PRIORITIES:
            raise ValidationFailed("priority must be low, normal, or high")
        now = utc_now()
        row = WorkspaceTaskModel(
            id=uuid4(),
            organization_id=organization_id,
            user_id=user_id,
            title=cleaned[:300],
            notes=notes,
            priority=priority,
            due_at=due_at,
            tag=(tag.strip()[:60] if tag and tag.strip() else None),
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return _dto(row)

    async def update(
        self,
        organization_id: TenantId,
        user_id: UserId,
        task_id: UUID,
        *,
        title: str | None = None,
        priority: str | None = None,
        due_at: datetime | None = None,
        tag: str | None = None,
        notes: str | None = None,
        completed: bool | None = None,
    ) -> TaskDTO:
        row = await self._get(organization_id, user_id, task_id)
        if title is not None:
            cleaned = title.strip()
            if not cleaned:
                raise ValidationFailed("title is required")
            row.title = cleaned[:300]
        if priority is not None:
            if priority not in _ALLOWED_PRIORITIES:
                raise ValidationFailed("priority must be low, normal, or high")
            row.priority = priority
        if due_at is not None:
            row.due_at = due_at
        if tag is not None:
            row.tag = tag.strip()[:60] if tag.strip() else None
        if notes is not None:
            row.notes = notes
        if completed is True:
            row.completed_at = utc_now()
        elif completed is False:
            row.completed_at = None
        row.updated_at = utc_now()
        await self._session.flush()
        return _dto(row)

    async def archive(self, organization_id: TenantId, user_id: UserId, task_id: UUID) -> None:
        row = await self._get(organization_id, user_id, task_id)
        row.archived_at = utc_now()
        row.updated_at = utc_now()
        await self._session.flush()

    async def _get(
        self, organization_id: TenantId, user_id: UserId, task_id: UUID
    ) -> WorkspaceTaskModel:
        row = await self._session.get(WorkspaceTaskModel, task_id)
        if (
            row is None
            or row.organization_id != organization_id
            or row.user_id != user_id
        ):
            raise NotFoundError("task not found")
        return row
