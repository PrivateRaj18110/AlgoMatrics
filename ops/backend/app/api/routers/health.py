"""Health check router."""

from fastapi import APIRouter

from app.schemas.health import HealthResponse
from app.services.health_service import get_health

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse, summary="Service health check")
def health() -> HealthResponse:
    """Liveness probe.

    Returns the service status, API version and current server time. Used by the
    frontend connection indicator and by container / load-balancer health checks.
    """
    return get_health()
