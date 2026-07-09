"""Attach OWASP security response headers to every response."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from algo_platform.shared.infrastructure.security_headers import security_headers

# Interactive docs need a relaxed CSP to render; these are dev/test-only paths.
_DOCS_PATHS = frozenset({"/docs", "/redoc", "/openapi.json"})


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, app_env: str) -> None:
        super().__init__(app)
        self._app_env = app_env

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        is_docs = request.url.path in _DOCS_PATHS
        for name, value in security_headers(self._app_env, is_docs=is_docs).items():
            # Never clobber a header a handler set deliberately.
            response.headers.setdefault(name, value)
        return response
