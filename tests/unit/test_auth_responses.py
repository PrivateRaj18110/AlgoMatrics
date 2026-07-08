from datetime import timedelta
from uuid import uuid4

from algo_platform.modules.identity.application.dto import IssuedTokensDTO, UserProfileDTO
from algo_platform.modules.identity.presentation.auth_router import _browser_tokens
from algo_platform.shared.domain.types import utc_now


def test_browser_token_response_does_not_expose_refresh_secret() -> None:
    now = utc_now()
    issued = IssuedTokensDTO(
        access_token="access-token",
        access_expires_at=now + timedelta(minutes=15),
        refresh_token="server-only-refresh-secret",
        refresh_expires_at=now + timedelta(days=30),
        session_id=uuid4(),
        user=UserProfileDTO(
            id=uuid4(),
            email="trader@example.com",
            full_name="Trader",
            status="active",
            email_verified=True,
            mfa_enabled=False,
            avatar_url=None,
            timezone="Asia/Calcutta",
            theme="system",
            preferences={},
            notification_settings={},
            is_platform_admin=False,
            created_at=now,
            last_login_at=now,
        ),
    )

    response = _browser_tokens(issued)

    assert response.refresh_token is None
    assert response.access_token == "access-token"
