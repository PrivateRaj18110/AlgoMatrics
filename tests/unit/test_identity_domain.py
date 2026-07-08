"""Domain tests for the identity aggregate: users, sessions, refresh-token
rotation, one-time e-mail tokens, and API keys."""

from __future__ import annotations

from uuid import uuid4

import pytest

from algo_platform.modules.identity.domain.users import (
    ApiKey,
    AuthSession,
    EmailToken,
    EmailTokenPurpose,
    RefreshToken,
    User,
    UserStatus,
)
from algo_platform.shared.domain.errors import (
    AuthenticationFailed,
    ConflictError,
    InvariantViolation,
)
from algo_platform.shared.domain.types import UserId, utc_now


def _user() -> User:
    return User.register(
        email="  Trader@Example.COM ", full_name="  Ada Trader ", password_hash="hash"
    )


class TestUser:
    def test_register_normalizes_email_and_name(self) -> None:
        user = _user()
        assert user.email == "trader@example.com"
        assert user.full_name == "Ada Trader"
        assert user.status is UserStatus.ACTIVE

    def test_register_requires_domain(self) -> None:
        with pytest.raises(InvariantViolation, match="domain"):
            User.register(email="nope", full_name="X", password_hash="h")

    def test_authentication_blocked_for_suspended_and_deactivated(self) -> None:
        user = _user()
        user.suspend()
        with pytest.raises(AuthenticationFailed, match="suspended"):
            user.ensure_can_authenticate()
        user.reactivate()
        user.status = UserStatus.DEACTIVATED
        with pytest.raises(AuthenticationFailed, match="deactivated"):
            user.ensure_can_authenticate()

    def test_email_verification_is_idempotent_guarded(self) -> None:
        user = _user()
        assert not user.is_email_verified
        user.mark_email_verified()
        assert user.is_email_verified
        with pytest.raises(ConflictError, match="already verified"):
            user.mark_email_verified()

    def test_change_password_stamps_time(self) -> None:
        user = _user()
        user.change_password("new-hash")
        assert user.password_hash == "new-hash"
        assert user.password_changed_at is not None

    def test_mfa_enable_then_disable(self) -> None:
        user = _user()
        user.enable_mfa(secret_ciphertext="c", wrapped_dek="d")
        assert user.mfa_enabled
        user.disable_mfa()
        assert not user.mfa_enabled
        assert user.mfa_secret_ciphertext is None
        with pytest.raises(ConflictError, match="not enabled"):
            user.disable_mfa()

    def test_suspend_twice_conflicts(self) -> None:
        user = _user()
        user.suspend()
        with pytest.raises(ConflictError, match="already suspended"):
            user.suspend()

    def test_record_login(self) -> None:
        user = _user()
        user.record_login()
        assert user.last_login_at is not None


class TestAuthSession:
    def test_lifecycle(self) -> None:
        session = AuthSession.start(user_id=UserId(uuid4()), user_agent="ua" * 500, ip_hash="h")
        assert len(session.user_agent) == 400
        assert session.is_active
        session.touch()
        session.revoke()
        assert not session.is_active
        revoked_at = session.revoked_at
        session.revoke()  # idempotent
        assert session.revoked_at == revoked_at


class TestRefreshToken:
    def _token(self, ttl_seconds: int = 3600) -> RefreshToken:
        return RefreshToken.issue(
            user_id=UserId(uuid4()),
            session_id=uuid4(),
            token_hash="hash",
            ttl_seconds=ttl_seconds,
        )

    def test_rotation_marks_used_and_links_replacement(self) -> None:
        original = self._token()
        replacement = self._token()
        assert not original.was_used
        original.rotate_to(replacement)
        assert original.was_used
        assert original.replaced_by_id == replacement.id
        assert original.revoked_at is not None

    def test_double_rotation_is_rejected(self) -> None:
        original = self._token()
        original.rotate_to(self._token())
        with pytest.raises(InvariantViolation, match="already rotated"):
            original.rotate_to(self._token())

    def test_expiry(self) -> None:
        assert self._token(ttl_seconds=-1).is_expired
        assert not self._token(ttl_seconds=3600).is_expired

    def test_family_id_is_preserved(self) -> None:
        family = uuid4()
        token = RefreshToken.issue(
            user_id=UserId(uuid4()),
            session_id=uuid4(),
            token_hash="h",
            ttl_seconds=60,
            family_id=family,
        )
        assert token.family_id == family


class TestEmailToken:
    def _token(self, ttl_seconds: int = 3600) -> EmailToken:
        return EmailToken.issue(
            user_id=UserId(uuid4()),
            purpose=EmailTokenPurpose.VERIFY_EMAIL,
            token_hash="hash",
            ttl_seconds=ttl_seconds,
        )

    def test_consume_once(self) -> None:
        token = self._token()
        token.consume()
        assert token.consumed_at is not None
        with pytest.raises(AuthenticationFailed, match="already used"):
            token.consume()

    def test_expired_token_rejected(self) -> None:
        with pytest.raises(AuthenticationFailed, match="expired"):
            self._token(ttl_seconds=-1).consume()


class TestApiKey:
    def _key(self, **overrides: object) -> ApiKey:
        base: dict[str, object] = {
            "id": uuid4(),
            "user_id": UserId(uuid4()),
            "organization_id": uuid4(),
            "name": "ci",
            "prefix": "ak_live",
            "key_hash": "hash",
            "scopes": ["read"],
        }
        base.update(overrides)
        return ApiKey(**base)  # type: ignore[arg-type]

    def test_active_by_default(self) -> None:
        assert self._key().is_active

    def test_expired_key_inactive(self) -> None:
        from datetime import timedelta

        assert not self._key(expires_at=utc_now() - timedelta(seconds=1)).is_active

    def test_revoke_once(self) -> None:
        key = self._key()
        key.revoke()
        assert not key.is_active
        with pytest.raises(ConflictError, match="already revoked"):
            key.revoke()
