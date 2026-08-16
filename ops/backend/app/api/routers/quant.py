"""AWS-side quant analytics and replay APIs."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.quant import (
    QuantAnalyticsSummary,
    QuantMarketReplay,
    QuantReportView,
    SyntheticReplayRequest,
    SyntheticReplayResult,
)
from app.services import quant_service
from app.services.quant_service import QuantNotFoundError, QuantValidationError

router = APIRouter(tags=["quant"])


def _raise_for(exc: Exception) -> None:
    if isinstance(exc, QuantNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, QuantValidationError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    raise exc


@router.get("/reports", response_model=list[QuantReportView], summary="List quant reports")
def list_quant_reports(
    limit: int = Query(100, ge=1, le=500),
    dataset_id: str | None = Query(default=None, alias="datasetId"),
) -> list[dict]:
    return quant_service.list_reports(limit=limit, dataset_id=dataset_id)


@router.get(
    "/analytics/{category}",
    response_model=QuantAnalyticsSummary,
    summary="Get read-only quant analytics for a category",
)
def get_quant_analytics(
    category: Literal[
        "performance",
        "strategy",
        "execution",
        "signals",
        "risk",
        "sessions",
        "dataQuality",
    ],
    limit: int = Query(100, ge=1, le=500),
    dataset_id: str | None = Query(default=None, alias="datasetId"),
) -> dict:
    try:
        return quant_service.analytics_summary(category, limit=limit, dataset_id=dataset_id)
    except Exception as exc:
        _raise_for(exc)
        raise


@router.get(
    "/datasets/{dataset_id}/report",
    response_model=QuantReportView,
    summary="Get latest quant report for a dataset",
)
def get_dataset_report(dataset_id: str) -> dict:
    try:
        return quant_service.get_dataset_report(dataset_id)
    except Exception as exc:
        _raise_for(exc)
        raise


@router.get(
    "/replays/datasets/{dataset_id}",
    response_model=QuantMarketReplay,
    summary="Get replay summary for a finalized dataset",
)
def get_dataset_replay(dataset_id: str) -> dict:
    try:
        return quant_service.get_dataset_report(dataset_id)["marketReplay"]
    except Exception as exc:
        _raise_for(exc)
        raise


@router.post(
    "/replays/synthetic",
    response_model=SyntheticReplayResult,
    summary="Run deterministic synthetic replay",
)
def run_synthetic_replay(payload: SyntheticReplayRequest) -> dict:
    return quant_service.synthetic_replay(payload)
