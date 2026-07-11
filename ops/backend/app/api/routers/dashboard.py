"""Dashboard router."""

from fastapi import APIRouter

from app.repositories import dashboard_doc
from app.schemas.dashboard import DashboardOverview
from app.services import algomatrics_service

router = APIRouter(tags=["dashboard"])


@router.get("/overview", response_model=DashboardOverview, summary="Dashboard overview")
def get_overview() -> dict:
    """Aggregated KPI + chart payload for the main dashboard.

    Served live from the AlgoMatrics control plane when configured, otherwise
    from the bundled mock fixture.
    """
    live = algomatrics_service.dashboard_overview()
    return live if live is not None else dashboard_doc
