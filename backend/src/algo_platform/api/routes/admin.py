"""Platform-admin composition endpoints (cross-tenant, admin-guarded)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text

from algo_platform.api.dependencies.auth import PlatformAdminDep
from algo_platform.api.dependencies.core import (
    MetricsDep,
    RedisDep,
    SessionDep,
    SettingsDep,
)
from algo_platform.api.dependencies.pagination import PageDep
from algo_platform.modules.audit.application.service import AuditService
from algo_platform.modules.billing.application.service import SubscriptionService
from algo_platform.modules.billing.domain.coupons import Coupon
from algo_platform.modules.billing.domain.plans import (
    Plan,
    PlanLimits,
    normalize_provider_prices,
)
from algo_platform.modules.billing.infrastructure.repositories import (
    SqlCouponRepository,
    SqlPlanRepository,
)
from algo_platform.modules.billing.presentation.router import ProvidersDep
from algo_platform.modules.brokerage.infrastructure.models import BrokerConnectionModel
from algo_platform.modules.identity.infrastructure.models import UserModel
from algo_platform.modules.identity.infrastructure.repositories import SqlUserRepository
from algo_platform.modules.notifications.application.service import NotificationService
from algo_platform.modules.organizations.infrastructure.models import OrganizationModel
from algo_platform.modules.strategies.infrastructure.models import StrategyRunModel
from algo_platform.shared.domain.errors import NotFoundError, ValidationFailed
from algo_platform.shared.domain.types import TenantId, UserId, utc_now
from algo_platform.shared.infrastructure.outbox import OutboxEventModel

router = APIRouter(prefix="/admin", tags=["admin"])


def _billing(
    session: SessionDep, redis: RedisDep, settings: SettingsDep, providers: ProvidersDep
) -> SubscriptionService:
    return SubscriptionService(
        session=session,
        providers=providers,
        app_base_url=settings.app_base_url,
        notifications=NotificationService(session, redis),
    )


# -- schemas ---------------------------------------------------------------------------


class AdminUserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    status: str
    email_verified: bool
    mfa_enabled: bool
    is_platform_admin: bool
    created_at: datetime
    last_login_at: datetime | None


class AdminOrganizationResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    created_at: datetime
    plan_code: str | None
    subscription_status: str | None


class AdminPlanRequest(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    price_monthly: Decimal = Field(ge=0)
    price_yearly: Decimal = Field(ge=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    features: list[str] = Field(default_factory=list)
    limits: dict[str, Any] = Field(default_factory=dict)
    provider_prices: dict[str, str] = Field(default_factory=dict)
    trial_days: int = Field(default=0, ge=0, le=90)
    sort_order: int = 0


class AdminPlanUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    price_monthly: Decimal | None = Field(default=None, ge=0)
    price_yearly: Decimal | None = Field(default=None, ge=0)
    features: list[str] | None = None
    limits: dict[str, Any] | None = None
    provider_prices: dict[str, str] | None = None
    trial_days: int | None = Field(default=None, ge=0, le=90)
    sort_order: int | None = None
    is_active: bool | None = None


class AdminPlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    description: str
    price_monthly: Decimal
    price_yearly: Decimal
    currency: str
    features: list[str]
    provider_prices: dict[str, str]
    trial_days: int
    is_active: bool
    sort_order: int


class AdminCouponRequest(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    description: str = Field(default="", max_length=300)
    percent_off: Decimal | None = Field(default=None, gt=0, le=100)
    amount_off: Decimal | None = Field(default=None, gt=0)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    max_redemptions: int | None = Field(default=None, ge=1)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    applies_plan_codes: list[str] = Field(default_factory=list)


class AdminCouponResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    description: str
    percent_off: Decimal | None
    amount_off: Decimal | None
    currency: str
    max_redemptions: int | None
    redeemed_count: int
    valid_from: datetime | None
    valid_until: datetime | None
    is_active: bool
    applies_plan_codes: list[str]


class GrantSubscriptionRequest(BaseModel):
    organization_id: UUID
    plan_code: str = Field(min_length=1, max_length=40)
    days: int = Field(ge=1, le=3650)
    note: str = Field(default="", max_length=300)


class SystemHealthResponse(BaseModel):
    database: bool
    redis: bool
    outbox_backlog: int
    market_data_age_seconds: float | None
    engine_heartbeat_age_seconds: float | None
    active_runs: int


class MessageResponse(BaseModel):
    message: str


# -- users -----------------------------------------------------------------------------


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(
    admin: PlatformAdminDep,
    session: SessionDep,
    page: PageDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> list[AdminUserResponse]:
    stmt = select(UserModel).order_by(UserModel.created_at.desc())
    if q:
        pattern = f"%{q.strip().lower()}%"
        stmt = stmt.where(UserModel.email.ilike(pattern) | UserModel.full_name.ilike(pattern))
    stmt = stmt.limit(page.limit).offset(page.offset)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        AdminUserResponse(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            status=u.status,
            email_verified=u.email_verified_at is not None,
            mfa_enabled=u.mfa_enabled,
            is_platform_admin=u.is_platform_admin,
            created_at=u.created_at,
            last_login_at=u.last_login_at,
        )
        for u in rows
    ]


@router.post("/users/{user_id}/suspend", response_model=MessageResponse)
async def suspend_user(
    user_id: UUID, request: Request, admin: PlatformAdminDep, session: SessionDep
) -> MessageResponse:
    users = SqlUserRepository(session)
    user = await users.get(UserId(user_id))
    if user is None:
        raise NotFoundError("user not found")
    user.suspend()
    await users.save(user)
    await AuditService(session).record(
        action="admin.user_suspended",
        resource_type="user",
        resource_id=str(user_id),
        actor_user_id=admin.user_id,
        request_id=getattr(request.state, "request_id", None),
    )
    return MessageResponse(message="user suspended")


@router.post("/users/{user_id}/reactivate", response_model=MessageResponse)
async def reactivate_user(
    user_id: UUID, request: Request, admin: PlatformAdminDep, session: SessionDep
) -> MessageResponse:
    users = SqlUserRepository(session)
    user = await users.get(UserId(user_id))
    if user is None:
        raise NotFoundError("user not found")
    user.reactivate()
    await users.save(user)
    await AuditService(session).record(
        action="admin.user_reactivated",
        resource_type="user",
        resource_id=str(user_id),
        actor_user_id=admin.user_id,
        request_id=getattr(request.state, "request_id", None),
    )
    return MessageResponse(message="user reactivated")


# -- organizations -----------------------------------------------------------------------


@router.get("/organizations", response_model=list[AdminOrganizationResponse])
async def list_organizations(
    admin: PlatformAdminDep, session: SessionDep, page: PageDep
) -> list[AdminOrganizationResponse]:
    from algo_platform.modules.billing.infrastructure.models import (
        PlanModel,
        SubscriptionModel,
    )

    stmt = (
        select(OrganizationModel, SubscriptionModel, PlanModel)
        .outerjoin(
            SubscriptionModel,
            SubscriptionModel.organization_id == OrganizationModel.id,
        )
        .outerjoin(PlanModel, PlanModel.id == SubscriptionModel.plan_id)
        .where(OrganizationModel.deleted_at.is_(None))
        .order_by(OrganizationModel.created_at.desc())
        .limit(page.limit)
        .offset(page.offset)
    )
    rows = (await session.execute(stmt)).all()
    return [
        AdminOrganizationResponse(
            id=org.id,
            name=org.name,
            slug=org.slug,
            created_at=org.created_at,
            plan_code=plan.code if plan else None,
            subscription_status=subscription.status if subscription else None,
        )
        for org, subscription, plan in rows
    ]


# -- plans ---------------------------------------------------------------------------------


@router.get("/plans", response_model=list[AdminPlanResponse])
async def list_plans_admin(admin: PlatformAdminDep, session: SessionDep) -> list[AdminPlanResponse]:
    plans = await SqlPlanRepository(session).list_all()
    return [AdminPlanResponse.model_validate(p) for p in plans]


@router.post("/plans", response_model=AdminPlanResponse, status_code=status.HTTP_201_CREATED)
async def create_plan(
    payload: AdminPlanRequest, admin: PlatformAdminDep, session: SessionDep
) -> AdminPlanResponse:
    repo = SqlPlanRepository(session)
    if await repo.get_by_code(payload.code) is not None:
        raise ValidationFailed("a plan with this code already exists")
    plan = Plan.create(
        code=payload.code,
        name=payload.name,
        description=payload.description,
        price_monthly=payload.price_monthly,
        price_yearly=payload.price_yearly,
        currency=payload.currency,
        features=payload.features,
        limits=PlanLimits.from_mapping(payload.limits),
        provider_prices=payload.provider_prices,
        trial_days=payload.trial_days,
        sort_order=payload.sort_order,
    )
    await repo.add(plan)
    return AdminPlanResponse.model_validate(plan)


@router.patch("/plans/{plan_id}", response_model=AdminPlanResponse)
async def update_plan(
    plan_id: UUID,
    payload: AdminPlanUpdateRequest,
    admin: PlatformAdminDep,
    session: SessionDep,
) -> AdminPlanResponse:
    repo = SqlPlanRepository(session)
    plan = await repo.get(plan_id)
    if plan is None:
        raise NotFoundError("plan not found")
    if payload.name is not None:
        plan.name = payload.name
    if payload.description is not None:
        plan.description = payload.description
    if payload.price_monthly is not None:
        plan.price_monthly = payload.price_monthly
    if payload.price_yearly is not None:
        plan.price_yearly = payload.price_yearly
    if payload.features is not None:
        plan.features = payload.features
    if payload.limits is not None:
        plan.limits = PlanLimits.from_mapping(payload.limits)
    if payload.provider_prices is not None:
        plan.provider_prices = normalize_provider_prices(payload.provider_prices)
    if payload.trial_days is not None:
        plan.trial_days = payload.trial_days
    if payload.sort_order is not None:
        plan.sort_order = payload.sort_order
    if payload.is_active is not None:
        plan.is_active = payload.is_active
    await repo.save(plan)
    return AdminPlanResponse.model_validate(plan)


# -- coupons ---------------------------------------------------------------------------------


@router.get("/coupons", response_model=list[AdminCouponResponse])
async def list_coupons(admin: PlatformAdminDep, session: SessionDep) -> list[AdminCouponResponse]:
    coupons = await SqlCouponRepository(session).list_all()
    return [AdminCouponResponse.model_validate(c) for c in coupons]


@router.post("/coupons", response_model=AdminCouponResponse, status_code=status.HTTP_201_CREATED)
async def create_coupon(
    payload: AdminCouponRequest, admin: PlatformAdminDep, session: SessionDep
) -> AdminCouponResponse:
    repo = SqlCouponRepository(session)
    if await repo.get_by_code(payload.code) is not None:
        raise ValidationFailed("a coupon with this code already exists")
    coupon = Coupon.create(
        code=payload.code,
        description=payload.description,
        percent_off=payload.percent_off,
        amount_off=payload.amount_off,
        currency=payload.currency,
        max_redemptions=payload.max_redemptions,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
        applies_plan_codes=payload.applies_plan_codes,
    )
    await repo.add(coupon)
    return AdminCouponResponse.model_validate(coupon)


@router.post("/coupons/{coupon_id}/deactivate", response_model=MessageResponse)
async def deactivate_coupon(
    coupon_id: UUID, admin: PlatformAdminDep, session: SessionDep
) -> MessageResponse:
    repo = SqlCouponRepository(session)
    coupon = await repo.get(coupon_id)
    if coupon is None:
        raise NotFoundError("coupon not found")
    coupon.is_active = False
    await repo.save(coupon)
    return MessageResponse(message="coupon deactivated")


# -- manual grants -----------------------------------------------------------------------------


@router.post("/subscriptions/grant", response_model=MessageResponse)
async def grant_subscription(
    payload: GrantSubscriptionRequest,
    request: Request,
    admin: PlatformAdminDep,
    session: SessionDep,
    redis: RedisDep,
    settings: SettingsDep,
    providers: ProvidersDep,
) -> MessageResponse:
    billing = _billing(session, redis, settings, providers)
    await billing.grant_manual_subscription(
        TenantId(payload.organization_id),
        plan_code=payload.plan_code,
        days=payload.days,
        note=payload.note,
    )
    await AuditService(session).record(
        action="admin.subscription_granted",
        resource_type="subscription",
        resource_id=str(payload.organization_id),
        organization_id=payload.organization_id,
        actor_user_id=admin.user_id,
        request_id=getattr(request.state, "request_id", None),
        after_state={"plan": payload.plan_code, "days": payload.days},
    )
    return MessageResponse(message="subscription granted")


# -- system health / metrics / monitoring ----------------------------------------------------------


@router.get("/health", response_model=SystemHealthResponse)
async def system_health(
    admin: PlatformAdminDep, session: SessionDep, redis: RedisDep
) -> SystemHealthResponse:
    database_ok = True
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        database_ok = False
    redis_ok = await redis.ping()

    backlog = int(
        (
            await session.execute(
                select(func.count())
                .select_from(OutboxEventModel)
                .where(OutboxEventModel.published_at.is_(None))
            )
        ).scalar_one()
    )
    market_age = await _heartbeat_age(redis, "hb:market_data")
    engine_age = await _heartbeat_age(redis, "hb:trading_engine")
    active_runs = int(
        (
            await session.execute(
                select(func.count())
                .select_from(StrategyRunModel)
                .where(StrategyRunModel.state.in_(["starting", "running", "paused"]))
            )
        ).scalar_one()
    )
    return SystemHealthResponse(
        database=database_ok,
        redis=redis_ok,
        outbox_backlog=backlog,
        market_data_age_seconds=market_age,
        engine_heartbeat_age_seconds=engine_age,
        active_runs=active_runs,
    )


async def _heartbeat_age(redis: RedisDep, key: str) -> float | None:
    raw = await redis.get_str(key)
    if raw is None:
        return None
    try:
        then = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return max(0.0, (utc_now() - then).total_seconds())


@router.get("/metrics", response_model=dict[str, int])
async def business_metrics(admin: PlatformAdminDep, metrics: MetricsDep) -> dict[str, int]:
    return await metrics.snapshot()


@router.get("/broker-connections", response_model=dict[str, int])
async def broker_connection_stats(admin: PlatformAdminDep, session: SessionDep) -> dict[str, int]:
    rows = (
        await session.execute(
            select(BrokerConnectionModel.status, func.count())
            .where(BrokerConnectionModel.deleted_at.is_(None))
            .group_by(BrokerConnectionModel.status)
        )
    ).all()
    return {str(status_): int(count) for status_, count in rows}


@router.get("/audit-events")
async def admin_audit_events(
    admin: PlatformAdminDep,
    session: SessionDep,
    page: PageDep,
    organization_id: Annotated[UUID | None, Query()] = None,
    action_prefix: Annotated[str | None, Query(max_length=60)] = None,
) -> dict[str, Any]:
    entries, total = await AuditService(session).search(
        organization_id=organization_id,
        action_prefix=action_prefix,
        limit=page.limit,
        offset=page.offset,
    )
    return {
        "total": total,
        "items": [
            {
                "id": str(e.id),
                "organization_id": str(e.organization_id) if e.organization_id else None,
                "actor_user_id": str(e.actor_user_id) if e.actor_user_id else None,
                "action": e.action,
                "resource_type": e.resource_type,
                "resource_id": e.resource_id,
                "request_id": e.request_id,
                "occurred_at": e.occurred_at.isoformat(),
            }
            for e in entries
        ],
    }
