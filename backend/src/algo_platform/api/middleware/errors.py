"""RFC 9457 problem-details mapping for domain and framework errors."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from algo_platform.shared.domain.errors import (
    AuthenticationFailed,
    ConflictError,
    DomainError,
    EntitlementExceeded,
    InvariantViolation,
    NotFoundError,
    PermissionDenied,
    RateLimited,
    UnavailableError,
    ValidationFailed,
)

logger = structlog.get_logger(__name__)

_STATUS_BY_ERROR: dict[type[DomainError], int] = {
    ValidationFailed: status.HTTP_422_UNPROCESSABLE_CONTENT,
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    AuthenticationFailed: status.HTTP_401_UNAUTHORIZED,
    PermissionDenied: status.HTTP_403_FORBIDDEN,
    RateLimited: status.HTTP_429_TOO_MANY_REQUESTS,
    EntitlementExceeded: status.HTTP_402_PAYMENT_REQUIRED,
    InvariantViolation: status.HTTP_409_CONFLICT,
    UnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
}

PROBLEM_CONTENT_TYPE = "application/problem+json"


def problem_response(
    request: Request,
    *,
    status_code: int,
    title: str,
    detail: str,
    code: str,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"urn:algo-matrics:error:{code}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "code": code,
        "request_id": getattr(request.state, "request_id", None),
    }
    if extra:
        body.update(extra)
    headers = {}
    if status_code == status.HTTP_401_UNAUTHORIZED:
        headers["WWW-Authenticate"] = "Bearer"
    return JSONResponse(
        status_code=status_code, content=body, media_type=PROBLEM_CONTENT_TYPE, headers=headers
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(request: Request, error: DomainError) -> JSONResponse:
        status_code = status.HTTP_400_BAD_REQUEST
        for error_type, mapped in _STATUS_BY_ERROR.items():
            if isinstance(error, error_type):
                status_code = mapped
                break
        extra: dict[str, Any] = {}
        if error.details:
            extra["errors"] = error.details
        response = problem_response(
            request,
            status_code=status_code,
            title=error.code.replace("_", " "),
            detail=error.message,
            code=error.code,
            extra=extra,
        )
        if isinstance(error, RateLimited):
            response.headers["Retry-After"] = str(error.retry_after_seconds)
        return response

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        return problem_response(
            request,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            title="request validation failed",
            detail="one or more request fields are invalid",
            code="request_invalid",
            extra={"errors": error.errors()},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request, error: StarletteHTTPException
    ) -> JSONResponse:
        return problem_response(
            request,
            status_code=error.status_code,
            title="http error",
            detail=str(error.detail),
            code="http_error",
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, error: Exception) -> JSONResponse:
        logger.exception("http.unhandled_error", path=request.url.path)
        return problem_response(
            request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            title="internal server error",
            detail="an unexpected error occurred; the incident was logged",
            code="internal_error",
        )
