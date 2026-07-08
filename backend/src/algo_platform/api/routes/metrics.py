"""Prometheus scrape endpoint.

Mounted at the root ``/metrics`` (Prometheus convention) rather than under the
``/api/v1`` prefix so it does not collide with the admin business-metrics JSON
endpoint at ``/api/v1/metrics``. Access is expected to be restricted to the
metrics network at the ingress/compose layer, not authenticated per request, so
Prometheus can scrape without credentials.
"""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from algo_platform.shared.infrastructure.prometheus import CONTENT_TYPE_LATEST, PrometheusMetrics

router = APIRouter(tags=["observability"])


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics(request: Request) -> Response:
    prometheus: PrometheusMetrics | None = getattr(request.app.state, "prometheus", None)
    if prometheus is None:
        return Response(status_code=404)
    return Response(content=prometheus.render(), media_type=CONTENT_TYPE_LATEST)
