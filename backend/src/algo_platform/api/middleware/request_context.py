"""Request ID propagation, per-request structured logging, and timing metrics."""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from algo_platform.shared.infrastructure.metrics import MetricsRecorder
from algo_platform.shared.infrastructure.prometheus import PrometheusMetrics

logger = structlog.get_logger("http")

REQUEST_ID_HEADER = "X-Request-ID"
CORRELATION_ID_HEADER = "X-Correlation-ID"
# Health probes are high frequency and low value in logs/metrics; excluding them
# keeps request logs readable and avoids inflating latency histograms.
_QUIET_PATHS = frozenset({"/api/v1/health/live", "/api/v1/health/ready"})


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if _is_safe_request_id(incoming) else str(uuid.uuid4())
        # A correlation ID ties together every log/metric across services for a
        # single logical operation. It defaults to the request ID but honours an
        # upstream-provided value so a trace can span the whole platform.
        incoming_corr = request.headers.get(CORRELATION_ID_HEADER, "")
        correlation_id = incoming_corr if _is_safe_request_id(incoming_corr) else request_id
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id, correlation_id=correlation_id
        )

        prometheus = self._prometheus(request)
        started = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.exception(
                "http.request_failed",
                method=request.method,
                path=request.url.path,
                duration_ms=elapsed_ms,
            )
            self._record_prometheus(prometheus, request, status_code, started)
            raise
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers[CORRELATION_ID_HEADER] = correlation_id
        self._record_prometheus(prometheus, request, status_code, started)
        if request.url.path not in _QUIET_PATHS:
            logger.info(
                "http.request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=elapsed_ms,
            )
            await self._record_redis(request, response.status_code, elapsed_ms)
        return response

    @staticmethod
    def _prometheus(request: Request) -> PrometheusMetrics | None:
        return getattr(request.app.state, "prometheus", None)

    def _record_prometheus(
        self,
        prometheus: PrometheusMetrics | None,
        request: Request,
        status_code: int,
        started: float,
    ) -> None:
        if prometheus is None:
            return
        route = _route_template(request)
        prometheus.http_requests_total.labels(
            method=request.method, route=route, status=str(status_code)
        ).inc()
        prometheus.http_request_duration_seconds.labels(
            method=request.method, route=route
        ).observe(time.perf_counter() - started)

    async def _record_redis(self, request: Request, status_code: int, elapsed_ms: int) -> None:
        metrics: MetricsRecorder | None = getattr(request.app.state, "metrics", None)
        if metrics is None:
            return
        try:
            await metrics.incr("http_requests_total")
            if status_code >= 500:
                await metrics.incr("http_requests_5xx")
            await metrics.observe_ms("http_latency", elapsed_ms)
        except Exception:
            logger.warning("metrics.record_failed")


def _route_template(request: Request) -> str:
    """Return the low-cardinality route template, e.g. ``/api/v1/orders/{id}``.

    Unmatched paths (404s, probes for arbitrary URLs) collapse to a single
    ``unmatched`` label so a scanner cannot explode metric cardinality.
    """
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    return "unmatched"


def _is_safe_request_id(value: str) -> bool:
    return 0 < len(value) <= 64 and all(ch.isalnum() or ch in "-_" for ch in value)
