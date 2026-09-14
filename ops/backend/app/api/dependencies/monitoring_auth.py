"""Upload-only authentication for the monitoring.v1 ingress.

A monitoring credential is the narrowest identity in this system. It may write
observations for exactly one ``source_id`` and nothing else: it grants no read
access, no administrative access, no access to another source's data, and —
structurally, since no such route exists — no control over LLS.

Fail closed. An unconfigured server rejects every upload rather than accepting
every upload, matching ``agent_auth.py`` and for the same reason: the failure
mode of the alternative is a public unauthenticated write path that looks
healthy.

Nothing here logs, echoes or returns a credential.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Header, HTTPException, Request, status

from app.core.config import get_settings
from app.core.security import hash_token

# One opaque message for every failure mode. Distinguishing "missing" from
# "invalid" from "unconfigured" tells an unauthenticated caller how far it got.
_UNAUTHORIZED = "monitoring upload authentication required"


@dataclass(frozen=True, slots=True)
class MonitoringPrincipal:
    """An authenticated monitoring publisher."""

    source_id: str
    organisation_id: UUID
    #: Environments this credential may publish into. Empty means unrestricted,
    #: in which case the declared environment is still stored and queried
    #: separately — it is simply not additionally constrained by the credential.
    environments: frozenset[str]
    request_id: str
    remote_addr: str | None

    def authorizes_source(self, claimed: str | None) -> bool:
        """True when the body's ``source_id`` matches this credential's scope."""
        if not claimed:
            return False
        return claimed.strip() == self.source_id

    def authorizes_environment(self, environment: str | None) -> bool:
        if not self.environments:
            return True
        return bool(environment) and environment.strip().lower() in self.environments


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=_UNAUTHORIZED,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_monitoring_publisher(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
) -> MonitoringPrincipal:
    """Authenticate a monitoring.v1 upload, or raise 401.

    The presented bearer token is hashed and looked up by digest, so comparison
    time does not vary with how much of a real credential was guessed.
    """
    import uuid

    settings = get_settings()
    index = settings.monitoring_token_index
    if not index:  # unconfigured means closed
        raise _unauthorized()

    presented = _bearer(authorization)
    if not presented:
        raise _unauthorized()

    source_id = index.get(hash_token(presented))
    if source_id is None:
        raise _unauthorized()

    try:
        organisation_id = settings.monitoring_source_organisation_index.get(source_id)
    except ValueError:
        raise _unauthorized()
    if organisation_id is None:
        # Fail-closed: unmapped publisher source is rejected.
        raise _unauthorized()

    request_id = (x_request_id or "").strip()[:64] or uuid.uuid4().hex
    client = request.client
    return MonitoringPrincipal(
        source_id=source_id,
        organisation_id=organisation_id,
        environments=settings.monitoring_environment_scope(source_id),
        request_id=request_id,
        remote_addr=client.host if client else None,
    )


@dataclass(frozen=True, slots=True)
class MonitoringAdmin:
    """An operator authorised to inspect quarantined material."""

    subject: str


async def require_monitoring_admin(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> MonitoringAdmin:
    """Authenticate an administrator, or raise 401/503.

    Quarantined material is, by definition, data the receiver could not
    interpret — possibly malformed, possibly hostile. It is visible only to this
    identity, which is deliberately **not** derivable from an upload credential:
    a publisher must never be able to read back what the receiver rejected from
    other publishers.
    """
    digest = get_settings().monitoring_admin_digest
    if not digest:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="monitoring administration is not configured on this deployment",
        )
    presented = _bearer(authorization)
    if not presented or hash_token(presented) != digest:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="monitoring administration credential required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return MonitoringAdmin(subject="monitoring-admin")


def _bearer(header: str | None) -> str:
    """Extract a bearer token, tolerating case differences in the scheme."""
    value = (header or "").strip()
    if not value:
        return ""
    scheme, _, token = value.partition(" ")
    if scheme.lower() != "bearer":
        return ""
    return token.strip()
