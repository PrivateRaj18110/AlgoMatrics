"""RS256 access-token issuance and verification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt

from algo_platform.shared.domain.errors import AuthenticationFailed
from algo_platform.shared.domain.types import utc_now

_ALGORITHM = "RS256"
_KEY_ID = "v1"


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    user_id: UUID
    session_id: UUID
    email: str
    organization_id: UUID | None
    role: str | None
    is_platform_admin: bool
    token_id: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class IssuedAccessToken:
    token: str
    expires_at: datetime
    token_id: str


class JwtService:
    def __init__(
        self,
        *,
        private_key_pem: str,
        public_key_pem: str,
        issuer: str,
        audience: str,
        access_ttl_seconds: int,
    ) -> None:
        self._private_key = private_key_pem
        self._public_key = public_key_pem
        self._issuer = issuer
        self._audience = audience
        self._ttl = timedelta(seconds=access_ttl_seconds)

    def issue(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        email: str,
        organization_id: UUID | None,
        role: str | None,
        is_platform_admin: bool,
    ) -> IssuedAccessToken:
        now = utc_now()
        expires_at = now + self._ttl
        token_id = str(uuid4())
        payload: dict[str, object] = {
            "iss": self._issuer,
            "aud": self._audience,
            "sub": str(user_id),
            "sid": str(session_id),
            "jti": token_id,
            "email": email,
            "org": str(organization_id) if organization_id else None,
            "role": role,
            "adm": is_platform_admin,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        token = jwt.encode(
            payload, self._private_key, algorithm=_ALGORITHM, headers={"kid": _KEY_ID}
        )
        return IssuedAccessToken(token=token, expires_at=expires_at, token_id=token_id)

    def verify(self, token: str) -> AccessTokenClaims:
        try:
            payload = jwt.decode(
                token,
                self._public_key,
                algorithms=[_ALGORITHM],
                issuer=self._issuer,
                audience=self._audience,
                options={"require": ["exp", "iat", "sub", "sid", "jti"]},
            )
        except jwt.PyJWTError as error:
            raise AuthenticationFailed("invalid or expired access token") from error
        org_raw = payload.get("org")
        return AccessTokenClaims(
            user_id=UUID(str(payload["sub"])),
            session_id=UUID(str(payload["sid"])),
            email=str(payload.get("email", "")),
            organization_id=UUID(str(org_raw)) if org_raw else None,
            role=str(payload["role"]) if payload.get("role") else None,
            is_platform_admin=bool(payload.get("adm", False)),
            token_id=str(payload["jti"]),
            expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=UTC),
        )
