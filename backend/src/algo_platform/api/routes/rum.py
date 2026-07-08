"""Real-User-Monitoring intake for browser Web Vitals and client errors.

The SPA posts a small, bounded report (typically via ``navigator.sendBeacon``)
that is folded into Prometheus. The endpoint is unauthenticated because it runs
from every visitor's browser, so it is deliberately defensive: fixed metric
allowlist, bounded value ranges, capped array sizes, and a sanitised, low-
cardinality error-kind label.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field, field_validator

from algo_platform.shared.infrastructure.prometheus import PrometheusMetrics

router = APIRouter(tags=["observability"])

_KNOWN_ERROR_KINDS = frozenset({"error", "unhandledrejection", "resource", "other"})


class RumMetric(BaseModel):
    name: Literal["CLS", "LCP", "INP", "FCP", "TTFB", "FID", "LoadTime"]
    # CLS is a unitless score; the rest are milliseconds. One hour is a generous
    # upper bound that rejects nonsense while tolerating slow networks.
    value: float = Field(ge=0, le=3_600_000)


class RumError(BaseModel):
    kind: str = Field(default="other", max_length=40)

    @field_validator("kind")
    @classmethod
    def _normalise_kind(cls, value: str) -> str:
        slug = value.strip().lower()
        return slug if slug in _KNOWN_ERROR_KINDS else "other"


class RumReport(BaseModel):
    metrics: list[RumMetric] = Field(default_factory=list, max_length=25)
    errors: list[RumError] = Field(default_factory=list, max_length=25)


@router.post("/rum", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False)
async def ingest_rum(report: RumReport, request: Request) -> Response:
    prometheus: PrometheusMetrics | None = getattr(request.app.state, "prometheus", None)
    if prometheus is not None:
        for metric in report.metrics:
            prometheus.frontend_web_vitals.labels(metric=metric.name).observe(metric.value)
        for error in report.errors:
            prometheus.frontend_errors_total.labels(kind=error.kind).inc()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
