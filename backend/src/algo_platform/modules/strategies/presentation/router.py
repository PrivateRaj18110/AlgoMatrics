from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field

from algo_platform.api.dependencies.core import RedisDep, SessionDep, SettingsDep
from algo_platform.api.dependencies.tenant import TenantContext, require_permission
from algo_platform.modules.audit.application.service import AuditService
from algo_platform.modules.billing.application.service import SubscriptionService
from algo_platform.modules.billing.presentation.router import ProvidersDep
from algo_platform.modules.notifications.application.service import NotificationService
from algo_platform.modules.organizations.domain.roles import Permission
from algo_platform.modules.risk.application.service import RiskService
from algo_platform.modules.strategies.application.service import StrategyService
from algo_platform.modules.strategies.infrastructure.artifact_store import ArtifactStore
from algo_platform.shared.domain.errors import PermissionDenied, ValidationFailed
from algo_platform.shared.domain.types import AccountId

router = APIRouter(tags=["strategies"])

StrategiesViewTenant = Annotated[
    TenantContext, Depends(require_permission(Permission.STRATEGIES_VIEW))
]
StrategiesManageTenant = Annotated[
    TenantContext, Depends(require_permission(Permission.STRATEGIES_MANAGE))
]


def get_strategy_service(
    session: SessionDep,
    redis: RedisDep,
    settings: SettingsDep,
    providers: ProvidersDep,
) -> StrategyService:
    billing = SubscriptionService(
        session=session,
        providers=providers,
        app_base_url=settings.app_base_url,
        notifications=NotificationService(session, redis),
    )
    return StrategyService(
        session=session,
        redis=redis,
        billing=billing,
        risk=RiskService(session),
        artifacts=ArtifactStore(settings.strategy_artifact_dir),
        # The only implemented source is simulated. A future venue feed must
        # explicitly satisfy freshness/sequence guarantees before enabling this.
        live_market_data_available=False,
    )


StrategyServiceDep = Annotated[StrategyService, Depends(get_strategy_service)]


class StrategyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str
    tags: list[str]
    status: str
    created_at: datetime
    updated_at: datetime
    latest_version: int
    active_runs: int


class CreateStrategyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    tags: list[str] = Field(default_factory=list)
    builtin_entry_point: str | None = Field(default=None, max_length=300)


class UpdateStrategyRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    tags: list[str] | None = None
    status: str | None = Field(default=None, pattern="^(draft|active|archived)$")


class StrategyVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    strategy_id: UUID
    version: int
    source: str
    entry_point: str
    checksum: str
    manifest: dict[str, Any]
    approved_for_live: bool
    created_at: datetime


class CreateBuiltinVersionRequest(BaseModel):
    entry_point: str = Field(min_length=1, max_length=300)


class StrategyRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    strategy_id: UUID
    strategy_name: str
    strategy_version_id: UUID
    strategy_version: int
    account_id: UUID
    mode: str
    state: str
    parameters: dict[str, Any]
    instrument_ids: list[str]
    timeframe: str
    started_at: datetime | None
    stopped_at: datetime | None
    last_heartbeat_at: datetime | None
    error: str | None
    stats: dict[str, Any]
    created_at: datetime


class CreateRunRequest(BaseModel):
    strategy_version_id: UUID
    account_id: UUID
    parameters: dict[str, Any] = Field(default_factory=dict)
    instrument_ids: list[UUID] = Field(min_length=1, max_length=20)
    timeframe: str = Field(default="1m", pattern="^(tick|1m|5m|15m|1h)$")
    autostart: bool = True


class StrategyLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    level: str
    message: str
    context: dict[str, Any]
    logged_at: datetime


class BuiltinManifestResponse(BaseModel):
    name: str
    entry_point: str
    description: str
    required_data: list[str]
    parameters: list[dict[str, Any]]


class MessageResponse(BaseModel):
    message: str


# -- strategy definitions ------------------------------------------------------------


@router.get("/strategies/builtin", response_model=list[BuiltinManifestResponse])
async def builtin_catalog(
    tenant: StrategiesViewTenant, service: StrategyServiceDep
) -> list[BuiltinManifestResponse]:
    return [BuiltinManifestResponse(**m) for m in service.builtin_catalog()]


@router.get("/strategies", response_model=list[StrategyResponse])
async def list_strategies(
    tenant: StrategiesViewTenant, service: StrategyServiceDep
) -> list[StrategyResponse]:
    strategies = await service.list_strategies(tenant.organization_id)
    return [StrategyResponse.model_validate(s) for s in strategies]


@router.post("/strategies", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
async def create_strategy(
    payload: CreateStrategyRequest,
    request: Request,
    tenant: StrategiesManageTenant,
    service: StrategyServiceDep,
    session: SessionDep,
) -> StrategyResponse:
    strategy = await service.create_strategy(
        tenant.organization_id,
        name=payload.name,
        description=payload.description,
        tags=payload.tags,
        created_by=tenant.user.user_id,
        builtin_entry_point=payload.builtin_entry_point,
    )
    await AuditService(session).record(
        action="strategies.created",
        resource_type="strategy",
        resource_id=str(strategy.id),
        organization_id=tenant.organization_id,
        actor_user_id=tenant.user.user_id,
        request_id=getattr(request.state, "request_id", None),
        after_state={"name": payload.name},
    )
    return StrategyResponse.model_validate(strategy)


@router.get("/strategies/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(
    strategy_id: UUID, tenant: StrategiesViewTenant, service: StrategyServiceDep
) -> StrategyResponse:
    strategy = await service.get_strategy(tenant.organization_id, strategy_id)
    return StrategyResponse.model_validate(strategy)


@router.patch("/strategies/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(
    strategy_id: UUID,
    payload: UpdateStrategyRequest,
    tenant: StrategiesManageTenant,
    service: StrategyServiceDep,
) -> StrategyResponse:
    strategy = await service.update_strategy(
        tenant.organization_id,
        strategy_id,
        name=payload.name,
        description=payload.description,
        tags=payload.tags,
        status=payload.status,
    )
    return StrategyResponse.model_validate(strategy)


@router.delete("/strategies/{strategy_id}", response_model=MessageResponse)
async def delete_strategy(
    strategy_id: UUID,
    request: Request,
    tenant: StrategiesManageTenant,
    service: StrategyServiceDep,
    session: SessionDep,
) -> MessageResponse:
    await service.delete_strategy(tenant.organization_id, strategy_id)
    await AuditService(session).record(
        action="strategies.deleted",
        resource_type="strategy",
        resource_id=str(strategy_id),
        organization_id=tenant.organization_id,
        actor_user_id=tenant.user.user_id,
        request_id=getattr(request.state, "request_id", None),
    )
    return MessageResponse(message="strategy archived and removed")


@router.post("/strategies/{strategy_id}/duplicate", response_model=StrategyResponse)
async def duplicate_strategy(
    strategy_id: UUID,
    tenant: StrategiesManageTenant,
    service: StrategyServiceDep,
) -> StrategyResponse:
    strategy = await service.duplicate_strategy(
        tenant.organization_id, strategy_id, created_by=tenant.user.user_id
    )
    return StrategyResponse.model_validate(strategy)


# -- versions --------------------------------------------------------------------------


@router.get("/strategies/{strategy_id}/versions", response_model=list[StrategyVersionResponse])
async def list_versions(
    strategy_id: UUID, tenant: StrategiesViewTenant, service: StrategyServiceDep
) -> list[StrategyVersionResponse]:
    versions = await service.list_versions(tenant.organization_id, strategy_id)
    return [StrategyVersionResponse.model_validate(v) for v in versions]


@router.post(
    "/strategies/{strategy_id}/versions/builtin",
    response_model=StrategyVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_builtin_version(
    strategy_id: UUID,
    payload: CreateBuiltinVersionRequest,
    tenant: StrategiesManageTenant,
    service: StrategyServiceDep,
) -> StrategyVersionResponse:
    version = await service.create_builtin_version(
        tenant.organization_id,
        strategy_id=strategy_id,
        entry_point=payload.entry_point,
        created_by=tenant.user.user_id,
    )
    return StrategyVersionResponse.model_validate(version)


@router.post(
    "/strategies/{strategy_id}/versions/upload",
    response_model=StrategyVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_version(
    strategy_id: UUID,
    tenant: StrategiesManageTenant,
    service: StrategyServiceDep,
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    file: UploadFile,
    entry_class: Annotated[str, Form(min_length=1, max_length=120)],
    parameters_json: Annotated[str, Form()] = "[]",
) -> StrategyVersionResponse:
    if not settings.allow_in_process_strategy_uploads:
        raise PermissionDenied(
            "strategy source uploads are disabled until an isolated strategy runner is configured"
        )
    raw = await file.read()
    try:
        source_code = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValidationFailed("strategy file must be UTF-8 Python source") from error
    try:
        parameters = json.loads(parameters_json)
    except json.JSONDecodeError as error:
        raise ValidationFailed("parameters_json must be valid JSON") from error
    if not isinstance(parameters, list):
        raise ValidationFailed("parameters_json must be a JSON array of parameter specs")
    version = await service.create_uploaded_version(
        tenant.organization_id,
        strategy_id=strategy_id,
        source_code=source_code,
        entry_class=entry_class,
        parameters=[dict(p) for p in parameters],
        created_by=tenant.user.user_id,
    )
    await AuditService(session).record(
        action="strategies.version_uploaded",
        resource_type="strategy_version",
        resource_id=str(version.id),
        organization_id=tenant.organization_id,
        actor_user_id=tenant.user.user_id,
        request_id=getattr(request.state, "request_id", None),
        after_state={"checksum": version.checksum},
    )
    return StrategyVersionResponse.model_validate(version)


# -- runs -------------------------------------------------------------------------------


@router.post(
    "/strategy-runs", response_model=StrategyRunResponse, status_code=status.HTTP_201_CREATED
)
async def create_run(
    payload: CreateRunRequest,
    request: Request,
    tenant: StrategiesManageTenant,
    service: StrategyServiceDep,
    session: SessionDep,
) -> StrategyRunResponse:
    run = await service.create_run(
        tenant.organization_id,
        strategy_version_id=payload.strategy_version_id,
        account_id=AccountId(payload.account_id),
        parameters=payload.parameters,
        instrument_ids=payload.instrument_ids,
        timeframe=payload.timeframe,
        created_by=tenant.user.user_id,
    )
    if payload.autostart:
        run = await service.start_run(tenant.organization_id, run.id)
    await AuditService(session).record(
        action="strategies.run_created",
        resource_type="strategy_run",
        resource_id=str(run.id),
        organization_id=tenant.organization_id,
        actor_user_id=tenant.user.user_id,
        request_id=getattr(request.state, "request_id", None),
        after_state={"mode": run.mode, "state": run.state},
    )
    return StrategyRunResponse.model_validate(run)


@router.get("/strategy-runs", response_model=list[StrategyRunResponse])
async def list_runs(
    tenant: StrategiesViewTenant,
    service: StrategyServiceDep,
    strategy_id: Annotated[UUID | None, Query()] = None,
    active_only: Annotated[bool, Query()] = False,
) -> list[StrategyRunResponse]:
    runs = await service.list_runs(
        tenant.organization_id, strategy_id=strategy_id, active_only=active_only
    )
    return [StrategyRunResponse.model_validate(r) for r in runs]


@router.get("/strategy-runs/{run_id}", response_model=StrategyRunResponse)
async def get_run(
    run_id: UUID, tenant: StrategiesViewTenant, service: StrategyServiceDep
) -> StrategyRunResponse:
    run = await service.get_run(tenant.organization_id, run_id)
    return StrategyRunResponse.model_validate(run)


@router.post("/strategy-runs/{run_id}/start", response_model=StrategyRunResponse)
async def start_run(
    run_id: UUID, tenant: StrategiesManageTenant, service: StrategyServiceDep
) -> StrategyRunResponse:
    run = await service.start_run(tenant.organization_id, run_id)
    return StrategyRunResponse.model_validate(run)


@router.post("/strategy-runs/{run_id}/pause", response_model=StrategyRunResponse)
async def pause_run(
    run_id: UUID, tenant: StrategiesManageTenant, service: StrategyServiceDep
) -> StrategyRunResponse:
    run = await service.pause_run(tenant.organization_id, run_id)
    return StrategyRunResponse.model_validate(run)


@router.post("/strategy-runs/{run_id}/resume", response_model=StrategyRunResponse)
async def resume_run(
    run_id: UUID, tenant: StrategiesManageTenant, service: StrategyServiceDep
) -> StrategyRunResponse:
    run = await service.resume_run(tenant.organization_id, run_id)
    return StrategyRunResponse.model_validate(run)


@router.post("/strategy-runs/{run_id}/stop", response_model=StrategyRunResponse)
async def stop_run(
    run_id: UUID, tenant: StrategiesManageTenant, service: StrategyServiceDep
) -> StrategyRunResponse:
    run = await service.stop_run(tenant.organization_id, run_id)
    return StrategyRunResponse.model_validate(run)


@router.get("/strategy-runs/{run_id}/logs", response_model=list[StrategyLogResponse])
async def run_logs(
    run_id: UUID,
    tenant: StrategiesViewTenant,
    service: StrategyServiceDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[StrategyLogResponse]:
    logs = await service.list_logs(tenant.organization_id, run_id, limit=limit, offset=offset)
    return [StrategyLogResponse.model_validate(entry) for entry in logs]
