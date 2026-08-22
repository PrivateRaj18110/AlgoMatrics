"""Business logic for service health.

Kept in a service layer (rather than inline in the router) so future checks —
database connectivity, broker gateways, message queues — slot in here without
touching the HTTP layer.
"""

from datetime import datetime, timezone

from app.core.config import get_settings
from app.schemas.health import HealthResponse


def get_health() -> HealthResponse:
    """Build the current health snapshot."""
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=settings.version,
        time=datetime.now(timezone.utc),
        environment=settings.environment,
    )
