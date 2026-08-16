"""Offline/recovery read API."""

from fastapi import APIRouter

from app.schemas.recovery import RecoverySummary
from app.services import recovery_service

router = APIRouter(tags=["recovery"])


@router.get("/summary", response_model=RecoverySummary, summary="Get recovery summary")
def get_recovery_summary() -> dict:
    return recovery_service.summary()
