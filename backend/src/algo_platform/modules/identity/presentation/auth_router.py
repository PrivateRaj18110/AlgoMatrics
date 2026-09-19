from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends, Request, Response, status

from algo_platform.api.dependencies.auth import CurrentUserDep
from algo_platform.api.dependencies.core import RedisDep, SessionDep, SettingsDep
from algo_platform.api.dependencies.rate_limit import rate_limit
from algo_platform.api.dependencies.tenant import TenantDep
from algo_platform.config import Settings
from algo_platform.modules.audit.application.service import AuditService
from algo_platform.modules.identity.application.auth_service import hash_ip, mask_email
from algo_platform.modules.identity.application.dto import IssuedTokensDTO
from algo_platform.modules.identity.presentation.dependencies import AuthServiceDep
from algo_platform.modules.identity.presentation.schemas import (
    EmailRequest,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    MfaCompleteRequest,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    RequestAccessRequest,
    ResetPasswordRequest,
    TokensResponse,
    VerifyEmailRequest,
    WsTicketResponse,
)
from algo_platform.modules.notifications.application.service import NotificationService
from algo_platform.modules.organizations.application.service import OrganizationService
from algo_platform.modules.organizations.presentation.dependencies import OrganizationServiceDep
from algo_platform.shared.domain.errors import (
    AuthenticationFailed,
    ConflictError,
    PermissionDenied,
    RateLimited,
    ValidationFailed,
)
from algo_platform.shared.domain.types import UserId
from algo_platform.shared.infrastructure.redis_gateway import RedisGateway

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "am_refresh"
DEVICE_COOKIE = "am_device"
_AUTH_COOKIE_PATH = "/api/v1/auth"
_DEVICE_COOKIE_MAX_AGE = 400 * 24 * 60 * 60

_ACCESS_REQUEST_RECEIVED = (
    "request received. The platform owner reviews every new account; you will get an "
    "e-mail when it is approved"
)


def _browser_tokens(tokens: IssuedTokensDTO) -> TokensResponse:
    """Return access/session data without exposing the refresh secret to JS."""
    response = TokensResponse.model_validate(tokens)
    return response.model_copy(update={"refresh_token": None})


def _set_refresh_cookie(response: Response, tokens: IssuedTokensDTO, settings: Settings) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        tokens.refresh_token,
        max_age=settings.refresh_token_ttl_seconds,
        path=_AUTH_COOKIE_PATH,
        domain=settings.cookie_domain,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def _set_device_cookie(response: Response, tokens: IssuedTokensDTO, settings: Settings) -> None:
    # Identifies the browser for new-device sign-in alerts. Not a credential:
    # it grants nothing, it only lets us recognise a browser we have seen.
    if tokens.device_token is None:
        return
    response.set_cookie(
        DEVICE_COOKIE,
        tokens.device_token,
        max_age=_DEVICE_COOKIE_MAX_AGE,
        path=_AUTH_COOKIE_PATH,
        domain=settings.cookie_domain,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        REFRESH_COOKIE,
        path=_AUTH_COOKIE_PATH,
        domain=settings.cookie_domain,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


async def _record_failed_sign_in(
    session: SessionDep,
    request: Request,
    *,
    email: str,
    error: AuthenticationFailed | RateLimited,
    stage: str,
) -> None:
    """Write a failed or blocked sign-in to the audit log, and keep it.

    The request is about to fail, which rolls the transaction back, so the
    entry is committed here explicitly. Nothing else has been written yet on
    these paths. The address is masked: the audit log is append-only.
    """
    reason = error.details.get("reason") if error.details else None
    await AuditService(session).record(
        action="auth.login_blocked" if isinstance(error, RateLimited) else "auth.login_failed",
        resource_type="user",
        request_id=getattr(request.state, "request_id", None),
        correlation_id=getattr(request.state, "correlation_id", None),
        ip_hash=hash_ip(_client_ip(request)),
        after_state={
            "email": mask_email(email),
            "stage": stage,
            "reason": str(reason or error.message),
        },
    )
    await session.commit()


async def _record_sign_in(
    session: SessionDep, request: Request, tokens: IssuedTokensDTO, *, mfa: bool
) -> None:
    await AuditService(session).record(
        action="auth.login",
        resource_type="user",
        resource_id=str(tokens.user.id),
        actor_user_id=tokens.user.id,
        request_id=getattr(request.state, "request_id", None),
        correlation_id=getattr(request.state, "correlation_id", None),
        session_id=str(tokens.session_id),
        ip_hash=hash_ip(_client_ip(request)),
        after_state={"mfa": mfa, "new_device": tokens.new_device},
    )


async def _notify_new_device(
    session: SessionDep,
    redis: RedisGateway,
    organizations: OrganizationService,
    tokens: IssuedTokensDTO,
) -> None:
    """In-app counterpart of the new-device e-mail, in each of the user's orgs."""
    if not tokens.new_device:
        return
    try:
        async with session.begin_nested():
            notifications = NotificationService(session, redis)
            for org in await organizations.list_for_user(UserId(tokens.user.id)):
                await notifications.notify(
                    organization_id=org.id,
                    user_id=tokens.user.id,
                    title="New sign-in to your account",
                    body=(
                        "Your account was signed in from a browser or device not seen "
                        "before. If this was not you, reset your password and sign out "
                        "other sessions under Settings → Security."
                    ),
                    type_="security",
                    severity="warning",
                )
    except Exception:
        # Advisory only: the e-mail alert already went out with the sign-in.
        logger.warning("auth.new_device_notification_failed", user_id=str(tokens.user.id))


@router.post(
    "/register",
    response_model=RegisterResponse,
    dependencies=[Depends(rate_limit("register", times=5, seconds=300))],
)
async def register(_payload: RegisterRequest) -> RegisterResponse:
    raise PermissionDenied("public signup is disabled")


@router.post(
    "/request-access",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("request-access", times=5, seconds=900))],
)
async def request_access(
    payload: RequestAccessRequest,
    request: Request,
    auth: AuthServiceDep,
    organizations: OrganizationServiceDep,
    session: SessionDep,
) -> MessageResponse:
    """Ask for an account. It stays locked until the platform owner approves it."""
    if payload.invitation_token:
        # The invitation link proves control of the invited address, so the
        # account starts verified and joins the organization immediately. It
        # still cannot sign in until the platform owner approves it.
        invitation = await organizations.preview_invitation(payload.invitation_token)
        user = await auth.request_access(
            email=invitation.email,
            password=payload.password,
            full_name=payload.full_name,
            email_verified=True,
        )
        if user is None:
            raise ConflictError(
                "an account already exists for this e-mail; sign in to accept the invitation"
            )
        await organizations.accept_invitation(
            raw_token=payload.invitation_token, user_id=user.id, user_email=user.email
        )
        via = f"invitation:{invitation.organization_name}"
    else:
        if payload.email is None:
            raise ValidationFailed("an e-mail address is required")
        user = await auth.request_access(
            email=payload.email, password=payload.password, full_name=payload.full_name
        )
        via = "request"
    if user is not None:
        await AuditService(session).record(
            action="auth.access_requested",
            resource_type="user",
            resource_id=str(user.id),
            actor_user_id=user.id,
            request_id=getattr(request.state, "request_id", None),
            ip_hash=hash_ip(_client_ip(request)),
            after_state={"via": via},
        )
    # Identical answer whether or not the address already had an account.
    return MessageResponse(message=_ACCESS_REQUEST_RECEIVED)


@router.post(
    "/login",
    response_model=LoginResponse,
    dependencies=[Depends(rate_limit("login", times=10, seconds=60))],
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    auth: AuthServiceDep,
    organizations: OrganizationServiceDep,
    session: SessionDep,
    redis: RedisDep,
    settings: SettingsDep,
) -> LoginResponse:
    try:
        result = await auth.login(
            email=payload.email,
            password=payload.password,
            user_agent=request.headers.get("User-Agent", ""),
            ip=_client_ip(request),
            device_token=request.cookies.get(DEVICE_COOKIE),
        )
    except (AuthenticationFailed, RateLimited) as error:
        await _record_failed_sign_in(
            session, request, email=payload.email, error=error, stage="password"
        )
        raise
    if result.kind == "tokens" and result.tokens is not None:
        _set_refresh_cookie(response, result.tokens, settings)
        _set_device_cookie(response, result.tokens, settings)
        await _record_sign_in(session, request, result.tokens, mfa=False)
        await _notify_new_device(session, redis, organizations, result.tokens)
        return LoginResponse(kind="tokens", tokens=_browser_tokens(result.tokens))
    return LoginResponse(kind="mfa_required", mfa_token=result.mfa_token)


@router.post(
    "/mfa/complete",
    response_model=TokensResponse,
    dependencies=[Depends(rate_limit("mfa", times=10, seconds=60))],
)
async def complete_mfa(
    payload: MfaCompleteRequest,
    request: Request,
    response: Response,
    auth: AuthServiceDep,
    organizations: OrganizationServiceDep,
    session: SessionDep,
    redis: RedisDep,
    settings: SettingsDep,
) -> TokensResponse:
    try:
        tokens = await auth.complete_mfa_login(
            mfa_token=payload.mfa_token,
            code=payload.code,
            user_agent=request.headers.get("User-Agent", ""),
            ip=_client_ip(request),
            device_token=request.cookies.get(DEVICE_COOKIE),
        )
    except AuthenticationFailed as error:
        # The challenge token is opaque; there is no address to record here.
        await _record_failed_sign_in(session, request, email="", error=error, stage="mfa")
        raise
    _set_refresh_cookie(response, tokens, settings)
    _set_device_cookie(response, tokens, settings)
    await _record_sign_in(session, request, tokens, mfa=True)
    await _notify_new_device(session, redis, organizations, tokens)
    return _browser_tokens(tokens)


@router.post("/refresh", response_model=TokensResponse)
async def refresh(
    request: Request,
    response: Response,
    auth: AuthServiceDep,
    settings: SettingsDep,
    payload: RefreshRequest | None = None,
) -> TokensResponse:
    raw = request.cookies.get(REFRESH_COOKIE) or (payload.refresh_token if payload else None)
    if not raw:
        raise AuthenticationFailed("refresh token missing")
    tokens = await auth.refresh(raw_refresh_token=raw)
    _set_refresh_cookie(response, tokens, settings)
    return _browser_tokens(tokens)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    user: CurrentUserDep,
    auth: AuthServiceDep,
    session: SessionDep,
    settings: SettingsDep,
) -> MessageResponse:
    if user.session_id is not None:
        await auth.logout(session_id=user.session_id)
        await AuditService(session).record(
            action="auth.logout",
            resource_type="user",
            resource_id=str(user.user_id),
            actor_user_id=user.user_id,
            request_id=getattr(request.state, "request_id", None),
        )
    _clear_refresh_cookie(response, settings)
    return MessageResponse(message="signed out")


@router.post(
    "/verify-email",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit("verify-email", times=10, seconds=300))],
)
async def verify_email(payload: VerifyEmailRequest, auth: AuthServiceDep) -> MessageResponse:
    await auth.verify_email(payload.token)
    return MessageResponse(message="e-mail address verified; you can sign in now")


@router.post(
    "/resend-verification",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit("resend-verification", times=3, seconds=300))],
)
async def resend_verification(payload: EmailRequest, auth: AuthServiceDep) -> MessageResponse:
    await auth.resend_verification(payload.email)
    return MessageResponse(message="if the address exists and is unverified, a new link was sent")


@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit("forgot-password", times=5, seconds=300))],
)
async def forgot_password(payload: EmailRequest, auth: AuthServiceDep) -> MessageResponse:
    await auth.request_password_reset(payload.email)
    return MessageResponse(message="if the address exists, a reset link was sent")


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    dependencies=[Depends(rate_limit("reset-password", times=5, seconds=300))],
)
async def reset_password(payload: ResetPasswordRequest, auth: AuthServiceDep) -> MessageResponse:
    await auth.reset_password(raw_token=payload.token, new_password=payload.new_password)
    return MessageResponse(message="password updated; sign in with your new password")


@router.post("/ws-ticket", response_model=WsTicketResponse)
async def ws_ticket(tenant: TenantDep, auth: AuthServiceDep) -> WsTicketResponse:
    ticket = await auth.issue_ws_ticket(
        user_id=tenant.user.user_id, organization_id=tenant.organization_id
    )
    return WsTicketResponse(ticket=ticket)
