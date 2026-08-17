"""Analytics router."""

from fastapi import APIRouter

from app.core.mock_policy import allow_mock_fixtures, empty_analytics
from app.repositories import analytics_doc
from app.schemas.analytics import AnalyticsData
from app.services import algomatrics_service

router = APIRouter(tags=["analytics"])


@router.get("", response_model=AnalyticsData, summary="Analytics dataset")
def get_analytics() -> dict:
    if not allow_mock_fixtures():
        live = algomatrics_service.analytics()
        return live if live is not None else empty_analytics()
    live = algomatrics_service.analytics()
    return live if live is not None else analytics_doc
