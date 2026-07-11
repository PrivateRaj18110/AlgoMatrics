"""Analytics router."""

from fastapi import APIRouter

from app.repositories import analytics_doc
from app.schemas.analytics import AnalyticsData
from app.services import algomatrics_service

router = APIRouter(tags=["analytics"])


@router.get("", response_model=AnalyticsData, summary="Analytics dataset")
def get_analytics() -> dict:
    live = algomatrics_service.analytics()
    return live if live is not None else analytics_doc
