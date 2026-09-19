"""Security center: account approvals, sign-in activity and live sessions.

Platform-admin only (and therefore MFA-gated). The read side is one overview
call so the page renders from a single consistent snapshot.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import func, select

from algo_platform.api.dependencies.auth import PlatformAdminDep
from algo_platform.api.dependencies.core import SessionDep, SettingsDep
from algo_platform.modules.audit.application.service import AuditService
from algo_platform.modules.audit.infrastructure.models import AuditLogModel
from algo_platform.modules.identity.application.access_service import AccessApprovalService
from algo_platform.modules.identity.domain.users import UserStatus
from algo_platform.modules.identity.infrastructure.models import SessionModel, UserModel
from algo_platform.modules.identity.infrastructure.repositories import SqlUserRepository
from algo_platform.modules.identity.presentation.dependencies import AuthServiceDep
from algo_platform.shared.domain.errors import NotFoundError
from algo_platform.shared.domain.types import UserId, utc_now
from algo_platform.shared.infrastructure.email_outbox import TransactionalEmailSender

router = APIRouter(prefix="/admin", tags=["admin-security"])

_RECENT_LIMIT = 25
_SESSION_LIMIT = 50


class MessageResponse(BaseModel):
    message: str


class SecurityCounts(BaseModel):
    users_total: int
    users_active: int
    users_pending: int
    users_suspended: int
    active_sessions: int
    sign_ins_24h: int
    failed_24h: int
    blocked_24h: int


class AccessRequestItem(BaseModel):
    id: UUID
    email: str
    full_name: str
    email_verified: bool
    requested_at: datetime


class AdminPostureItem(BaseModel):
    id: UUID
    email: str
    full_name: str
    mfa_enabled: bool


class SignInItem(BaseModel):
    occurred_at: datetime
    user_id: UUID | None
    email: str | None
    full_name: str | None
    mfa: bool
    new_device: bool
    network: str | None


class FailedAttemptItem(BaseModel):
    occurred_at: datetime
    blocked: bool
    email: str
    stage: str
    reason: str
    network: str | None


class ActiveSessionItem(BaseModel):
    id: UUID
    user_id: UUID
    email: str
    full_name: str
    user_agent: str
    created_at: datetime
    last_seen_at: datetime
    is_current: bool


class SecurityOverviewResponse(BaseModel):
    generated_at: datetime
    require_mfa_for_admins: bool
    counts: SecurityCounts
    access_requests: list[AccessRequestItem]
    admins: list[AdminPostureItem]
    recent_sign_ins: list[SignInItem]
    failed_attempts: list[FailedAttemptItem]
    active_sessions: list[ActiveSessionItem]


def _network(ip_hash: str | None) -> str | None:
    # A short, stable tag: lets an admin see "same network as before" without
    # the raw IP ever having been stored.
    return ip_hash[:8] if ip_hash else None


def _state(entry: AuditLogModel) -> dict[str, Any]:
    return entry.after_state or {}


@router.get("/security/overview", response_model=SecurityOverviewResponse)
async def security_overview(
    admin: PlatformAdminDep, session: SessionDep, settings: SettingsDep
) -> SecurityOverviewResponse:
    since = utc_now() - timedelta(hours=24)

    status_counts = dict(
        (await session.execute(select(UserModel.status, func.count()).group_by(UserModel.status)))
        .tuples()
        .all()
    )
    event_counts = dict(
        (
            await session.execute(
                select(AuditLogModel.action, func.count())
                .where(
                    AuditLogModel.action.in_(
                        ("auth.login", "auth.login_failed", "auth.login_blocked")
                    ),
                    AuditLogModel.occurred_at >= since,
                )
                .group_by(AuditLogModel.action)
            )
        )
        .tuples()
        .all()
    )
    active_session_count = int(
        (
            await session.execute(
                select(func.count())
                .select_from(SessionModel)
                .where(SessionModel.revoked_at.is_(None))
            )
        ).scalar_one()
    )

    pending = (
        (
            await session.execute(
                select(UserModel)
                .where(UserModel.status == UserStatus.PENDING_APPROVAL.value)
                .order_by(UserModel.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    admins = (
        (
            await session.execute(
                select(UserModel)
                .where(UserModel.is_platform_admin.is_(True))
                .order_by(UserModel.email)
            )
        )
        .scalars()
        .all()
    )

    sign_in_rows = (
        await session.execute(
            select(AuditLogModel, UserModel)
            .outerjoin(UserModel, UserModel.id == AuditLogModel.actor_user_id)
            .where(AuditLogModel.action == "auth.login")
            .order_by(AuditLogModel.occurred_at.desc())
            .limit(_RECENT_LIMIT)
        )
    ).all()
    failed_rows = (
        (
            await session.execute(
                select(AuditLogModel)
                .where(AuditLogModel.action.in_(("auth.login_failed", "auth.login_blocked")))
                .order_by(AuditLogModel.occurred_at.desc())
                .limit(_RECENT_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    session_rows = (
        await session.execute(
            select(SessionModel, UserModel)
            .join(UserModel, UserModel.id == SessionModel.user_id)
            .where(SessionModel.revoked_at.is_(None))
            .order_by(SessionModel.last_seen_at.desc())
            .limit(_SESSION_LIMIT)
        )
    ).all()

    return SecurityOverviewResponse(
        generated_at=utc_now(),
        require_mfa_for_admins=settings.require_mfa_for_admins,
        counts=SecurityCounts(
            users_total=sum(int(v) for v in status_counts.values()),
            users_active=int(status_counts.get(UserStatus.ACTIVE.value, 0)),
            users_pending=int(status_counts.get(UserStatus.PENDING_APPROVAL.value, 0)),
            users_suspended=int(status_counts.get(UserStatus.SUSPENDED.value, 0)),
            active_sessions=active_session_count,
            sign_ins_24h=int(event_counts.get("auth.login", 0)),
            failed_24h=int(event_counts.get("auth.login_failed", 0)),
            blocked_24h=int(event_counts.get("auth.login_blocked", 0)),
        ),
        access_requests=[
            AccessRequestItem(
                id=u.id,
                email=u.email,
                full_name=u.full_name,
                email_verified=u.email_verified_at is not None,
                requested_at=u.created_at,
            )
            for u in pending
        ],
        admins=[
            AdminPostureItem(
                id=u.id, email=u.email, full_name=u.full_name, mfa_enabled=u.mfa_enabled
            )
            for u in admins
        ],
        recent_sign_ins=[
            SignInItem(
                occurred_at=entry.occurred_at,
                user_id=entry.actor_user_id,
                email=user.email if user else None,
                full_name=user.full_name if user else None,
                mfa=bool(_state(entry).get("mfa", False)),
                new_device=bool(_state(entry).get("new_device", False)),
                network=_network(entry.ip_hash),
            )
            for entry, user in sign_in_rows
        ],
        failed_attempts=[
            FailedAttemptItem(
                occurred_at=entry.occurred_at,
                blocked=entry.action == "auth.login_blocked",
                email=str(_state(entry).get("email", "***")),
                stage=str(_state(entry).get("stage", "password")),
                reason=str(_state(entry).get("reason", "")),
                network=_network(entry.ip_hash),
            )
            for entry in failed_rows
        ],
        active_sessions=[
            ActiveSessionItem(
                id=s.id,
                user_id=s.user_id,
                email=u.email,
                full_name=u.full_name,
                user_agent=s.user_agent,
                created_at=s.created_at,
                last_seen_at=s.last_seen_at,
                is_current=s.id == admin.session_id,
            )
            for s, u in session_rows
        ],
    )


def _approvals(session: SessionDep, settings: SettingsDep) -> AccessApprovalService:
    return AccessApprovalService(
        users=SqlUserRepository(session),
        email_sender=TransactionalEmailSender(session),
        settings=settings,
    )


@router.post("/users/{user_id}/approve", response_model=MessageResponse)
async def approve_access(
    user_id: UUID,
    request: Request,
    admin: PlatformAdminDep,
    session: SessionDep,
    settings: SettingsDep,
) -> MessageResponse:
    user = await _approvals(session, settings).approve(UserId(user_id))
    await AuditService(session).record(
        action="admin.access_approved",
        resource_type="user",
        resource_id=str(user_id),
        actor_user_id=admin.user_id,
        request_id=getattr(request.state, "request_id", None),
        after_state={"status": user.status.value},
    )
    return MessageResponse(message=f"{user.email} can now sign in")


@router.post("/users/{user_id}/reject", response_model=MessageResponse)
async def reject_access(
    user_id: UUID,
    request: Request,
    admin: PlatformAdminDep,
    session: SessionDep,
    settings: SettingsDep,
) -> MessageResponse:
    user = await _approvals(session, settings).reject(UserId(user_id))
    await AuditService(session).record(
        action="admin.access_rejected",
        resource_type="user",
        resource_id=str(user_id),
        actor_user_id=admin.user_id,
        request_id=getattr(request.state, "request_id", None),
        after_state={"status": user.status.value},
    )
    return MessageResponse(message=f"request from {user.email} rejected")


@router.post("/sessions/{session_id}/revoke", response_model=MessageResponse)
async def revoke_session(
    session_id: UUID,
    request: Request,
    admin: PlatformAdminDep,
    session: SessionDep,
    auth: AuthServiceDep,
) -> MessageResponse:
    target = await session.get(SessionModel, session_id)
    if target is None:
        raise NotFoundError("session not found")
    await auth.logout(session_id=session_id)
    await AuditService(session).record(
        action="admin.session_revoked",
        resource_type="session",
        resource_id=str(session_id),
        actor_user_id=admin.user_id,
        request_id=getattr(request.state, "request_id", None),
        after_state={"user_id": str(target.user_id)},
    )
    return MessageResponse(message="session signed out")
