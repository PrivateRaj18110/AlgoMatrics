from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from algo_platform.api.dependencies.core import SessionDep
from algo_platform.api.dependencies.tenant import TenantDep
from algo_platform.modules.workspace.application.service import WorkspaceTaskService

router = APIRouter(prefix="/tasks", tags=["workspace"])


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class CreateTaskRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    notes: str | None = Field(default=None, max_length=2000)
    priority: str = "normal"
    due_at: datetime | None = None
    tag: str | None = Field(default=None, max_length=60)


class UpdateTaskRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    notes: str | None = None
    priority: str | None = None
    due_at: datetime | None = None
    tag: str | None = None
    completed: bool | None = None


class MessageResponse(BaseModel):
    message: str


@router.get("", response_model=list[TaskResponse])
async def list_tasks(tenant: TenantDep, session: SessionDep) -> list[TaskResponse]:
    items = await WorkspaceTaskService(session).list_for_user(
        tenant.organization_id, tenant.user.user_id
    )
    return [TaskResponse.model_validate(item) for item in items]


@router.post("", response_model=TaskResponse, status_code=201)
async def create_task(
    payload: CreateTaskRequest, tenant: TenantDep, session: SessionDep
) -> TaskResponse:
    item = await WorkspaceTaskService(session).create(
        tenant.organization_id,
        tenant.user.user_id,
        title=payload.title,
        notes=payload.notes,
        priority=payload.priority,
        due_at=payload.due_at,
        tag=payload.tag,
    )
    return TaskResponse.model_validate(item)


@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: UUID, payload: UpdateTaskRequest, tenant: TenantDep, session: SessionDep
) -> TaskResponse:
    item = await WorkspaceTaskService(session).update(
        tenant.organization_id,
        tenant.user.user_id,
        task_id,
        title=payload.title,
        notes=payload.notes,
        priority=payload.priority,
        due_at=payload.due_at,
        tag=payload.tag,
        completed=payload.completed,
    )
    return TaskResponse.model_validate(item)


@router.delete("/{task_id}", response_model=MessageResponse)
async def archive_task(task_id: UUID, tenant: TenantDep, session: SessionDep) -> MessageResponse:
    await WorkspaceTaskService(session).archive(
        tenant.organization_id, tenant.user.user_id, task_id
    )
    return MessageResponse(message="archived")
