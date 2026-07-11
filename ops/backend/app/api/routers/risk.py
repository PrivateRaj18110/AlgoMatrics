"""Risk router."""

from fastapi import APIRouter

from app.repositories import risk_doc
from app.schemas.risk import RiskData
from app.services import algomatrics_service

router = APIRouter(tags=["risk"])


@router.get("/overview", response_model=RiskData, summary="Risk overview")
def get_risk() -> dict:
    live = algomatrics_service.risk_overview()
    return live if live is not None else risk_doc
