"""Viewer authentication for the live telemetry websocket.

``/api/ws`` streams machine state, trades and events. Before this module it was
open to anyone who could reach the host, which — with the ops API published at
``/ops/api`` — meant anyone on the internet.

Two credential forms are accepted, both fail-closed:

``RAJ_DASHBOARD_TOKEN``
    A shared viewer token. Works today with no new dependency and no key
    distribution. **Limitation:** a token shipped to a browser SPA is a shared
    secret, not a per-user identity — it authenticates "a dashboard", not "a
    person", and it cannot be revoked for one user. It is a large improvement
    over anonymous access and an honest interim, not the end state.

``OPS_JWT_PUBLIC_KEY`` (preferred, when available)
    The platform issues RS256 access tokens
    (``algo_platform.shared.infrastructure.jwt_service``). Verification needs
    only the *public* key, so no secret crosses the service boundary and the ops
    API gains real per-user identity and expiry. PyJWT is imported lazily: if the
    key is unset or the library is absent, this path is simply unavailable and
    the token path still applies.

**Transport.** Browsers cannot set headers on a ``WebSocket``, and putting a
credential in the query string would leak it into access logs, proxy logs and
`Referer` headers. The credential therefore travels in the
``Sec-WebSocket-Protocol`` header as ``raj-token,<credential>`` — a standard,
header-based channel every browser supports. A plain ``Authorization`` header is
also accepted for non-browser clients (tests, CLI probes).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import Header, HTTPException, status

from app.core.config import get_settings
from app.core.security import hash_token, token_matches

# The subprotocol name that marks the second protocol entry as a credential.
CREDENTIAL_SUBPROTOCOL = "raj-token"


@dataclass(frozen=True, slots=True)
class Viewer:
    """A dashboard/API viewer.

    ``permissions`` is intentionally coarse today. Shared-token viewers get a
    bounded read permission; JWT viewers can carry future platform/RBAC claims
    without replacing this dependency.
    """

    subject: str
    kind: str  # "anonymous" | "token" | "jwt"
    permissions: frozenset[str] = field(default_factory=frozenset)


def extract_credential(
    subprotocol_header: str | None,
    authorization_header: str | None,
) -> tuple[str | None, str | None]:
    """Pull the credential out of a websocket handshake.

    Returns ``(credential, negotiated_subprotocol)``. The negotiated value must
    be echoed back on accept or the browser fails the handshake.
    """
    if subprotocol_header:
        parts = [p.strip() for p in subprotocol_header.split(",") if p.strip()]
        if len(parts) >= 2 and parts[0] == CREDENTIAL_SUBPROTOCOL:
            return parts[1], CREDENTIAL_SUBPROTOCOL
    if authorization_header:
        scheme, _, value = authorization_header.partition(" ")
        if scheme.lower() in {"bearer", "token"} and value.strip():
            return value.strip(), None
    return None, None


def extract_rest_credential(
    authorization_header: str | None,
    dashboard_token_header: str | None,
) -> str | None:
    """Pull a dashboard credential out of a REST request.

    Browser fetches can use ``Authorization: Bearer``. Local probes and older
    reverse-proxy setups may use ``X-Raj-Dashboard-Token``. Query-string tokens
    are deliberately unsupported because they leak into access logs.
    """
    if dashboard_token_header and dashboard_token_header.strip():
        return dashboard_token_header.strip()
    if authorization_header:
        scheme, _, value = authorization_header.partition(" ")
        if scheme.lower() in {"bearer", "token"} and value.strip():
            return value.strip()
    return None


def _verify_jwt(credential: str) -> Viewer | None:
    """Verify a platform RS256 access token. ``None`` when unavailable/invalid."""
    settings = get_settings()
    public_key = (settings.ops_jwt_public_key or "").strip()
    if not public_key:
        return None
    try:  # lazy: PyJWT is optional for deployments using the token path only
        import jwt
    except ImportError:
        return None
    options = {"require": ["exp", "sub"]}
    kwargs: dict[str, object] = {"algorithms": ["RS256"], "options": options}
    if settings.ops_jwt_issuer:
        kwargs["issuer"] = settings.ops_jwt_issuer
    if settings.ops_jwt_audience:
        kwargs["audience"] = settings.ops_jwt_audience
    else:
        # Without a configured audience, don't fail tokens that carry one.
        options["verify_aud"] = False
    try:
        claims = jwt.decode(credential, public_key, **kwargs)  # type: ignore[arg-type]
    except Exception:
        return None
    permissions = claims.get("permissions") or claims.get("scope") or []
    if isinstance(permissions, str):
        parsed_permissions = frozenset(part for part in permissions.split() if part)
    elif isinstance(permissions, list):
        parsed_permissions = frozenset(str(part) for part in permissions)
    else:
        parsed_permissions = frozenset()
    return Viewer(subject=str(claims.get("sub", "")), kind="jwt", permissions=parsed_permissions)


def authenticate_viewer(credential: str | None) -> Viewer | None:
    """Authenticate a websocket subscriber. ``None`` means reject.

    Fail-closed: with neither credential form configured, every subscriber is
    rejected — the websocket is never quietly left open.
    """
    settings = get_settings()
    if not settings.dashboard_auth_configured:
        return None
    if not credential:
        return None

    shared = (settings.raj_dashboard_token or "").strip()
    if shared and token_matches(credential, hash_token(shared)):
        # Identify the viewer by a short digest prefix — never the credential.
        return Viewer(
            subject=f"token:{hash_token(credential)[:12]}",
            kind="token",
            permissions=frozenset({"ops:read"}),
        )

    return _verify_jwt(credential)


def rest_auth_required() -> bool:
    """Whether REST dashboard reads must authenticate in this environment."""
    settings = get_settings()
    return settings.is_production or settings.ops_rest_auth_required


def require_dashboard_viewer(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_raj_dashboard_token: str | None = Header(default=None, alias="X-Raj-Dashboard-Token"),
) -> Viewer:
    """FastAPI dependency for dashboard REST APIs.

    Development/mock mode may remain anonymous unless ``OPS_REST_AUTH_REQUIRED``
    is enabled. Production always requires a valid viewer credential. If a
    credential is supplied but invalid, reject it even when auth is optional so
    bad deployments fail loudly.
    """
    credential = extract_rest_credential(authorization, x_raj_dashboard_token)
    required = rest_auth_required()
    if not credential and not required:
        return Viewer(subject="anonymous", kind="anonymous")

    viewer = authenticate_viewer(credential)
    if viewer is not None:
        return viewer

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="dashboard authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )
