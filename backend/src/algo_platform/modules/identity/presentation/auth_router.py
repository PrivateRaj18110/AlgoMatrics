from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status

from algo_platform.api.dependencies.auth import CurrentUserDep
from algo_platform.api.dependencies.core import SessionDep, SettingsDep
from algo_platform.api.dependencies.rate_limit import rate_limit
from algo_platform.api.dependencies.tenant import TenantDep
from algo_platform.config import Settings
from algo_platform.modules.audit.application.service import AuditService
from algo_platform.modules.identity.application.auth_service import hash_ip
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
    ResetPasswordRequest,
    TokensResponse,
    VerifyEmailRequest,
    WsTicketResponse,
)
from algo_platform.modules.organizations.presentation.dependencies import (
    OrganizationServiceDep,
)
from algo_platform.shared.domain.errors import AuthenticationFailed

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "am_refresh"
_REFRESH_COOKIE_PATH = "/api/v1/auth"


def _browser_tokens(tokens: IssuedTokensDTO) -> TokensResponse:
    """Return access/session data without exposing the refresh secret to JS."""
    response = TokensResponse.model_validate(tokens)
    return response.model_copy(update={"refresh_token": None})


def _set_refresh_cookie(response: Response, tokens: IssuedTokensDTO, settings: Settings) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        tokens.refresh_token,
        max_age=settings.refresh_token_ttl_seconds,
        path=_REFRESH_COOKIE_PATH,
        domain=settings.cookie_domain,
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )


def _clear_refresh_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        REFRESH_COOKIE,
        path=_REFRESH_COOKIE_PATH,
        domain=settings.cookie_domain,
    )


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("register", times=5, seconds=300))],
)
async def register(
    payload: RegisterRequest,
    request: Request,
    auth: AuthServiceDep,
    organizations: OrganizationServiceDep,
    session: SessionDep,
) -> RegisterResponse:
    user = await auth.register(
        email=payload.email, password=payload.password, full_name=payload.full_name
    )
    org_name = payload.organization_name or f"{payload.full_name.split(' ')[0]}'s Workspace"
    organization = await organizations.create_organization(name=org_name, owner_user_id=user.id)
    await AuditService(session).record(
        action="auth.register",
        resource_type="user",
        resource_id=str(user.id),
        organization_id=organization.id,
        actor_user_id=user.id,
        request_id=getattr(request.state, "request_id", None),
        ip_hash=hash_ip(request.client.host if request.client else None),
    )
    return RegisterResponse(
        user_id=user.id,
        message="account created; check your inbox to verify your e-mail address",
    )


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
    session: SessionDep,
    settings: SettingsDep,
) -> LoginResponse:
    result = await auth.login(
        email=payload.email,
        password=payload.password,
        user_agent=request.headers.get("User-Agent", ""),
        ip=request.client.host if request.client else None,
    )
    if result.kind == "tokens" and result.tokens is not None:
        _set_refresh_cookie(response, result.tokens, settings)
        await AuditService(session).record(
            action="auth.login",
            resource_type="user",
            resource_id=str(result.tokens.user.id),
            actor_user_id=result.tokens.user.id,
            request_id=getattr(request.state, "request_id", None),
            ip_hash=hash_ip(request.client.host if request.client else None),
        )
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
    settings: SettingsDep,
) -> TokensResponse:
    tokens = await auth.complete_mfa_login(
        mfa_token=payload.mfa_token,
        code=payload.code,
        user_agent=request.headers.get("User-Agent", ""),
        ip=request.client.host if request.client else None,
    )
    _set_refresh_cookie(response, tokens, settings)
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
