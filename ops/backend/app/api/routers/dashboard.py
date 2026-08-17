"""Dashboard router."""

from fastapi import APIRouter

from app.core.mock_policy import allow_mock_fixtures, empty_dashboard
from app.repositories import dashboard_doc
from app.schemas.dashboard import DashboardOverview
from app.services import algomatrics_service

router = APIRouter(tags=["dashboard"])


@router.get("/overview", response_model=DashboardOverview, summary="Dashboard overview")
def get_overview() -> dict:
    if not allow_mock_fixtures():
        live = algomatrics_service.dashboard_overview()
        return live if live is not None else empty_dashboard()
    live = algomatrics_service.dashboard_overview()
    return live if live is not None else dashboard_doc
