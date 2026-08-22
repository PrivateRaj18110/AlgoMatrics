"""Risk router."""

from fastapi import APIRouter

from app.core.mock_policy import allow_mock_fixtures, empty_risk
from app.repositories import risk_doc
from app.schemas.risk import RiskData
from app.services import algomatrics_service

router = APIRouter(tags=["risk"])


@router.get("/overview", response_model=RiskData, summary="Risk overview")
def get_risk() -> dict:
    if not allow_mock_fixtures():
        live = algomatrics_service.risk_overview()
        return live if live is not None else empty_risk()
    live = algomatrics_service.risk_overview()
    return live if live is not None else risk_doc
