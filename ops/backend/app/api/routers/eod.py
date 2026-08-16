"""EOD dataset landing and reconciliation API.

Write endpoints are agent-authenticated and machine-scoped. Read endpoints feed
the ops dashboard with catalog/reconciliation state only.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.api.dependencies.agent_auth import (
    AgentPrincipal,
    enforce_machine_scope,
    require_agent_token,
)
from app.api.dependencies.dashboard_auth import Viewer, require_dashboard_viewer
from app.core.config import get_settings
from app.schemas.eod import (
    DatasetStatus,
    EodActionResult,
    EodDatasetView,
    EodManifestRegister,
    EodQuarantineRequest,
    EodReconciliationSummary,
    EodUploadAck,
)
from app.services import eod_service
from app.services.eod_service import EodConflictError, EodNotFoundError, EodValidationError

router = APIRouter(tags=["eod"])
AgentAuth = Annotated[AgentPrincipal, Depends(require_agent_token)]
DashboardAuth = Annotated[Viewer, Depends(require_dashboard_viewer)]


def _raise_for(exc: Exception) -> None:
    if isinstance(exc, EodNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, EodConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    if isinstance(exc, EodValidationError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    raise exc


@router.get("/datasets", response_model=list[EodDatasetView], summary="List EOD datasets")
def list_eod_datasets(
    _viewer: DashboardAuth,
    limit: int = Query(100, ge=1, le=500),
    dataset_status: DatasetStatus | None = Query(default=None, alias="status"),
    machine_id: str | None = Query(default=None, alias="machineId"),
    trading_date: str | None = Query(default=None, alias="tradingDate"),
) -> list[dict]:
    return eod_service.list_datasets(
        limit=limit,
        status=dataset_status,
        machine_id=machine_id,
        trading_date=trading_date,
    )


@router.get(
    "/datasets/{dataset_id}",
    response_model=EodDatasetView,
    summary="Get EOD dataset detail",
)
def get_eod_dataset(
    dataset_id: str,
    _viewer: DashboardAuth,
) -> dict:
    try:
        return eod_service.get_dataset(dataset_id)
    except Exception as exc:
        _raise_for(exc)
        raise


@router.get(
    "/reconciliation",
    response_model=EodReconciliationSummary,
    summary="Get EOD reconciliation summary",
)
def get_eod_reconciliation(
    _viewer: DashboardAuth,
) -> dict:
    return eod_service.reconciliation()


@router.post(
    "/discoveries",
    response_model=EodDatasetView,
    summary="Record a discovered EOD dataset before manifest registration",
)
async def discover_eod_dataset(
    payload: EodManifestRegister,
    principal: AgentAuth,
) -> dict:
    enforce_machine_scope(principal, payload.machine)
    try:
        return eod_service.discover_dataset(payload)
    except Exception as exc:
        _raise_for(exc)
        raise


@router.post(
    "/manifests",
    response_model=EodDatasetView,
    summary="Register an EOD dataset manifest",
)
async def register_eod_manifest(
    payload: EodManifestRegister,
    principal: AgentAuth,
) -> dict:
    enforce_machine_scope(principal, payload.machine)
    try:
        return eod_service.register_manifest(payload)
    except Exception as exc:
        _raise_for(exc)
        raise


@router.put(
    "/datasets/{dataset_id}/files/{file_id}/chunks",
    response_model=EodUploadAck,
    summary="Upload an EOD file chunk",
)
async def upload_eod_chunk(
    dataset_id: str,
    file_id: str,
    request: Request,
    principal: AgentAuth,
    offset: int = Query(0, ge=0),
) -> dict:
    try:
        dataset = eod_service.get_dataset(dataset_id)
        enforce_machine_scope(principal, dataset.get("machine"))
        body = await request.body()
        if len(body) > get_settings().eod_max_chunk_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="EOD chunk exceeds configured maximum",
            )
        return eod_service.upload_chunk(dataset_id, file_id, offset, body)
    except HTTPException:
        raise
    except Exception as exc:
        _raise_for(exc)
        raise


@router.post(
    "/datasets/{dataset_id}/complete",
    response_model=EodActionResult,
    summary="Mark an EOD dataset upload attempt complete",
)
async def complete_eod_dataset(
    dataset_id: str,
    principal: AgentAuth,
) -> dict:
    try:
        dataset = eod_service.get_dataset(dataset_id)
        enforce_machine_scope(principal, dataset.get("machine"))
        return {"dataset": eod_service.complete_dataset(dataset_id)}
    except Exception as exc:
        _raise_for(exc)
        raise


@router.post(
    "/datasets/{dataset_id}/quarantine",
    response_model=EodActionResult,
    summary="Quarantine an unsafe or invalid EOD dataset",
)
async def quarantine_eod_dataset(
    dataset_id: str,
    payload: EodQuarantineRequest,
    principal: AgentAuth,
) -> dict:
    try:
        dataset = eod_service.get_dataset(dataset_id)
        enforce_machine_scope(principal, dataset.get("machine"))
        return {"dataset": eod_service.quarantine_dataset(dataset_id, payload.reason)}
    except Exception as exc:
        _raise_for(exc)
        raise


@router.post(
    "/datasets/{dataset_id}/finalize",
    response_model=EodActionResult,
    summary="Finalize a validated EOD dataset",
)
async def finalize_eod_dataset(
    dataset_id: str,
    principal: AgentAuth,
) -> dict:
    try:
        dataset = eod_service.get_dataset(dataset_id)
        enforce_machine_scope(principal, dataset.get("machine"))
        return {"dataset": eod_service.finalize_dataset(dataset_id)}
    except Exception as exc:
        _raise_for(exc)
        raise
