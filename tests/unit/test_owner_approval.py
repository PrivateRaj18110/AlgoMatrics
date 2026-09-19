"""Owner approval of new accounts, new-device alerts and the admin MFA gate.

No database or Redis: collaborators are small fakes matching the surfaces the
code under test actually uses.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from algo_platform.api.dependencies import auth as auth_deps
from algo_platform.api.dependencies import tenant as tenant_deps
from algo_platform.modules.identity.application import auth_service as auth_module
from algo_platform.modules.identity.application.access_service import AccessApprovalService
from algo_platform.modules.identity.application.auth_service import AuthService, mask_email
from algo_platform.modules.identity.domain.users import User, UserStatus
from algo_platform.modules.organizations.domain.roles import Permission
from algo_platform.shared.application.ports import EmailMessage
from algo_platform.shared.domain.errors import (
    AuthenticationFailed,
    ConflictError,
    MfaRequired,
    PermissionDenied,
    ValidationFailed,
)
from algo_platform.shared.domain.types import UserId

STRONG = "Str0ngPassword"


def _pending(**kwargs: Any) -> User:
    return User.request_access(
        email="new@example.com", full_name="New Person", password_hash="hash", **kwargs
    )


class FakeUsers:
    def __init__(self, *users: User) -> None:
        self.by_id = {u.id: u for u in users}
        self.added: list[User] = []

    async def add(self, user: User) -> None:
        self.added.append(user)
        self.by_id[user.id] = user

    async def get(self, user_id: UserId) -> User | None:
        return self.by_id.get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        wanted = email.strip().lower()
        return next((u for u in self.by_id.values() if u.email == wanted), None)

    async def save(self, user: User) -> None:
        self.by_id[user.id] = user

    async def list_platform_admins(self) -> list[User]:
        return [u for u in self.by_id.values() if u.is_platform_admin]


class Outbox:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.sent.append(message)


class FakeEmailTokens:
    async def invalidate_for_user(self, *_: Any) -> None:
        return None

    async def add(self, _token: Any) -> None:
        return None


class FakeDeviceRedis:
    def __init__(self, *, broken: bool = False) -> None:
        self.hashes: dict[str, dict[str, dict[str, Any]]] = {}
        self.broken = broken

    async def hgetall_json(self, key: str) -> dict[str, dict[str, Any]]:
        if self.broken:
            raise ConnectionError("redis down")
        return dict(self.hashes.get(key, {}))

    async def hset_json(self, key: str, field: str, value: dict[str, Any]) -> None:
        self.hashes.setdefault(key, {})[field] = value

    async def expire(self, key: str, ttl_seconds: int) -> None:
        return None


SETTINGS = SimpleNamespace(app_base_url="https://console.test", require_mfa_for_admins=True)


def _auth(users: FakeUsers, outbox: Outbox, redis: Any = None) -> AuthService:
    service = AuthService.__new__(AuthService)
    service._users = users  # type: ignore[attr-defined]
    service._email_sender = outbox  # type: ignore[attr-defined]
    service._email_tokens = FakeEmailTokens()  # type: ignore[attr-defined]
    service._settings = SETTINGS  # type: ignore[attr-defined]
    service._session = None  # type: ignore[attr-defined]
    service._redis = redis  # type: ignore[attr-defined]
    return service


@pytest.fixture(autouse=True)
def _no_outbox_events(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop(*_: Any, **__: Any) -> None:
        return None

    monkeypatch.setattr(auth_module, "enqueue_event", _noop)


# -- domain ---------------------------------------------------------------------------


class TestPendingAccount:
    def test_request_access_starts_pending_and_unverified(self) -> None:
        user = _pending()
        assert user.status is UserStatus.PENDING_APPROVAL
        assert user.is_pending_approval
        assert not user.is_email_verified

    def test_invitation_path_starts_verified(self) -> None:
        assert _pending(email_verified=True).is_email_verified

    def test_pending_account_cannot_authenticate(self) -> None:
        with pytest.raises(AuthenticationFailed) as excinfo:
            _pending().ensure_can_authenticate()
        assert excinfo.value.details == {"reason": "pending_approval"}

    def test_approve_activates(self) -> None:
        user = _pending()
        user.approve()
        assert user.status is UserStatus.ACTIVE
        user.ensure_can_authenticate()  # no raise

    def test_reject_deactivates(self) -> None:
        user = _pending()
        user.reject()
        assert user.status is UserStatus.DEACTIVATED
        with pytest.raises(AuthenticationFailed):
            user.ensure_can_authenticate()

    @pytest.mark.parametrize("action", ["approve", "reject"])
    def test_only_pending_accounts_can_be_decided(self, action: str) -> None:
        active = User.register(email="a@example.com", full_name="A", password_hash="h")
        with pytest.raises(ConflictError):
            getattr(active, action)()

    def test_existing_accounts_are_unaffected(self) -> None:
        assert User.register(email="a@b.co", full_name="A", password_hash="h").status is (
            UserStatus.ACTIVE
        )


@pytest.mark.parametrize(
    ("raw", "masked"),
    [
        ("Raj@Example.com", "ra***@example.com"),
        ("a@example.com", "a***@example.com"),
        ("not-an-email", "***"),
        ("", "***"),
    ],
)
def test_mask_email(raw: str, masked: str) -> None:
    assert mask_email(raw) == masked


# -- request access -----------------------------------------------------------------------


async def test_request_access_creates_pending_user_and_tells_admins() -> None:
    admin = User.register(email="owner@example.com", full_name="Owner", password_hash="h")
    admin.is_platform_admin = True
    users, outbox = FakeUsers(admin), Outbox()

    user = await _auth(users, outbox).request_access(
        email="New@Example.com", password=STRONG, full_name="New Person"
    )

    assert user is not None and user.is_pending_approval
    assert users.added == [user]
    recipients = sorted(m.to for m in outbox.sent)
    # Verification link to the requester, review notice to the owner.
    assert recipients == ["new@example.com", "owner@example.com"]
    notice = next(m for m in outbox.sent if m.to == "owner@example.com")
    assert "/app/admin/security" in notice.text


async def test_request_access_for_existing_email_is_silent() -> None:
    existing = User.register(email="taken@example.com", full_name="T", password_hash="h")
    users, outbox = FakeUsers(existing), Outbox()

    result = await _auth(users, outbox).request_access(
        email="taken@example.com", password=STRONG, full_name="Someone"
    )

    assert result is None
    assert users.added == []
    assert outbox.sent == []  # nothing that would reveal the account exists


async def test_request_access_via_invitation_skips_verification_mail() -> None:
    users, outbox = FakeUsers(), Outbox()
    user = await _auth(users, outbox).request_access(
        email="invitee@example.com", password=STRONG, full_name="Invitee", email_verified=True
    )
    assert user is not None and user.is_email_verified
    assert all(m.to != "invitee@example.com" for m in outbox.sent)


async def test_request_access_enforces_password_policy() -> None:
    with pytest.raises(ValidationFailed):
        await _auth(FakeUsers(), Outbox()).request_access(
            email="x@example.com", password="short", full_name="X"
        )


# -- approval service ----------------------------------------------------------------------


async def test_approve_emails_the_person() -> None:
    user = _pending(email_verified=True)
    users, outbox = FakeUsers(user), Outbox()
    service = AccessApprovalService(users=users, email_sender=outbox, settings=SETTINGS)  # type: ignore[arg-type]

    approved = await service.approve(user.id)

    assert approved.status is UserStatus.ACTIVE
    assert [m.to for m in outbox.sent] == ["new@example.com"]
    assert "https://console.test/login" in outbox.sent[0].text


async def test_approve_reminds_unverified_people_to_verify() -> None:
    user = _pending()
    outbox = Outbox()
    service = AccessApprovalService(users=FakeUsers(user), email_sender=outbox, settings=SETTINGS)  # type: ignore[arg-type]
    await service.approve(user.id)
    assert "confirm your e-mail" in outbox.sent[0].text


async def test_reject_deactivates_and_emails() -> None:
    user = _pending()
    outbox = Outbox()
    service = AccessApprovalService(users=FakeUsers(user), email_sender=outbox, settings=SETTINGS)  # type: ignore[arg-type]
    rejected = await service.reject(user.id)
    assert rejected.status is UserStatus.DEACTIVATED
    assert "not approved" in outbox.sent[0].text


# -- new-device alerts ---------------------------------------------------------------------


def _active() -> User:
    return User.register(email="trader@example.com", full_name="Trader", password_hash="h")


async def test_first_tracked_sign_in_never_alerts() -> None:
    redis = FakeDeviceRedis()
    service = _auth(FakeUsers(), Outbox(), redis)
    token, alert = await service._recognise_device(_active(), device_token=None, user_agent="UA")
    assert token and not alert


async def test_unknown_browser_alerts_known_browser_does_not() -> None:
    redis = FakeDeviceRedis()
    user = _active()
    service = _auth(FakeUsers(), Outbox(), redis)
    laptop, _ = await service._recognise_device(user, device_token=None, user_agent="laptop")

    _, again = await service._recognise_device(user, device_token=laptop, user_agent="laptop")
    assert not again

    phone, alert = await service._recognise_device(user, device_token=None, user_agent="phone")
    assert alert and phone != laptop


async def test_oversized_device_cookie_is_replaced() -> None:
    service = _auth(FakeUsers(), Outbox(), FakeDeviceRedis())
    token, _ = await service._recognise_device(_active(), device_token="x" * 500, user_agent="UA")
    assert len(token) < 128


async def test_device_tracking_outage_never_blocks_or_alerts() -> None:
    service = _auth(FakeUsers(), Outbox(), FakeDeviceRedis(broken=True))
    token, alert = await service._recognise_device(_active(), device_token=None, user_agent="UA")
    assert token and not alert


async def test_new_device_alert_goes_to_the_account_owner() -> None:
    outbox = Outbox()
    service = _auth(FakeUsers(), outbox)
    await service._send_new_device_alert(_active(), user_agent="Firefox", ip="203.0.113.9")
    (mail,) = outbox.sent
    assert mail.to == "trader@example.com"
    assert "203.0.113.9" in mail.text and "Firefox" in mail.text


# -- MFA gate ------------------------------------------------------------------------------


def test_mfa_required_is_a_distinct_permission_denial() -> None:
    error = MfaRequired("x")
    assert isinstance(error, PermissionDenied)
    assert error.code == "mfa_required"


def _patch_user_lookup(monkeypatch: pytest.MonkeyPatch, user: User | None) -> None:
    class Repo:
        def __init__(self, _session: Any) -> None:
            pass

        async def get(self, _user_id: Any) -> User | None:
            return user

    monkeypatch.setattr(auth_deps, "SqlUserRepository", Repo)


async def test_admin_without_mfa_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    user = _active()
    _patch_user_lookup(monkeypatch, user)
    principal = SimpleNamespace(user_id=user.id)
    with pytest.raises(MfaRequired):
        await auth_deps.ensure_mfa_enabled(principal, None, SETTINGS)  # type: ignore[arg-type]


async def test_admin_with_mfa_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    user = _active()
    user.mfa_enabled = True
    _patch_user_lookup(monkeypatch, user)
    await auth_deps.ensure_mfa_enabled(SimpleNamespace(user_id=user.id), None, SETTINGS)  # type: ignore[arg-type]


async def test_mfa_gate_can_be_switched_off(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_user_lookup(monkeypatch, None)
    off = SimpleNamespace(require_mfa_for_admins=False)
    await auth_deps.ensure_mfa_enabled(SimpleNamespace(user_id=None), None, off)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("permission", "gated"),
    [
        (Permission.ORG_MANAGE, True),
        (Permission.MEMBERS_MANAGE, True),
        (Permission.BILLING_MANAGE, True),
        (Permission.TRADING_EXECUTE, False),
        (Permission.STRATEGIES_MANAGE, False),
        (Permission.API_KEYS_MANAGE, False),
    ],
)
async def test_only_management_permissions_require_mfa(
    monkeypatch: pytest.MonkeyPatch, permission: Permission, gated: bool
) -> None:
    calls: list[Any] = []

    async def fake_gate(user: Any, _session: Any, _settings: Any) -> None:
        calls.append(user)

    monkeypatch.setattr(tenant_deps, "ensure_mfa_enabled", fake_gate)
    tenant = SimpleNamespace(permissions=frozenset(Permission), user="principal")
    dependency = tenant_deps.require_permission(permission)
    assert await dependency(tenant, None, SETTINGS) is tenant  # type: ignore[arg-type]
    assert calls == (["principal"] if gated else [])
