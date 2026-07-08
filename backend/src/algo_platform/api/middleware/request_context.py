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

logger = structlog.get_logger("http")

REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, metrics: MetricsRecorder | None = None) -> None:
        super().__init__(app)
        self._metrics = metrics

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if _is_safe_request_id(incoming) else str(uuid.uuid4())
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.exception(
                "http.request_failed",
                method=request.method,
                path=request.url.path,
                duration_ms=elapsed_ms,
            )
            raise
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        response.headers[REQUEST_ID_HEADER] = request_id
        if request.url.path not in {"/api/v1/health/live", "/api/v1/health/ready"}:
            logger.info(
                "http.request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=elapsed_ms,
            )
            if self._metrics is not None:
                try:
                    await self._metrics.incr("http_requests_total")
                    if response.status_code >= 500:
                        await self._metrics.incr("http_requests_5xx")
                    await self._metrics.observe_ms("http_latency", elapsed_ms)
                except Exception:
                    logger.warning("metrics.record_failed")
        return response


def _is_safe_request_id(value: str) -> bool:
    return 0 < len(value) <= 64 and all(ch.isalnum() or ch in "-_" for ch in value)
