"""Domain error hierarchy.

Domain and application code raise these; the API layer maps them to RFC 9457
problem-details responses. Domain code never imports transport concerns.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar


class DomainError(Exception):
    code: ClassVar[str] = "domain_error"

    def __init__(self, message: str, *, details: Mapping[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, object] = dict(details or {})


class ValidationFailed(DomainError):
    code: ClassVar[str] = "validation_failed"


class NotFoundError(DomainError):
    code: ClassVar[str] = "not_found"


class ConflictError(DomainError):
    code: ClassVar[str] = "conflict"


class AuthenticationFailed(DomainError):
    code: ClassVar[str] = "authentication_failed"


class PermissionDenied(DomainError):
    code: ClassVar[str] = "permission_denied"


class RateLimited(DomainError):
    code: ClassVar[str] = "rate_limited"

    def __init__(
        self,
        message: str = "too many requests",
        *,
        retry_after_seconds: int = 60,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.retry_after_seconds = retry_after_seconds


class EntitlementExceeded(DomainError):
    """A plan limit or feature entitlement blocks the requested action."""

    code: ClassVar[str] = "entitlement_exceeded"


class InvariantViolation(DomainError):
    code: ClassVar[str] = "invariant_violation"
