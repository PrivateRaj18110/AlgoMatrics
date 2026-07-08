from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from algo_platform.api.dependencies.core import RedisDep, SessionDep, SettingsDep
from algo_platform.api.dependencies.pagination import PageDep
from algo_platform.api.dependencies.tenant import TenantContext, require_permission
from algo_platform.modules.audit.application.service import AuditService
from algo_platform.modules.billing.application.ports import PaymentProvider
from algo_platform.modules.billing.application.service import SubscriptionService
from algo_platform.modules.billing.domain.plans import BillingCycle
from algo_platform.modules.billing.infrastructure.providers.razorpay import RazorpayProvider
from algo_platform.modules.notifications.application.service import NotificationService
from algo_platform.modules.organizations.domain.roles import Permission
from algo_platform.shared.domain.errors import NotFoundError, ValidationFailed

router = APIRouter(prefix="/billing", tags=["billing"])

BillingTenant = Annotated[TenantContext, Depends(require_permission(Permission.BILLING_MANAGE))]
BillingViewTenant = Annotated[TenantContext, Depends(require_permission(Permission.ORG_VIEW))]


def get_payment_providers(request: Request) -> dict[str, PaymentProvider]:
    providers: dict[str, PaymentProvider] = request.app.state.payment_providers
    return providers


ProvidersDep = Annotated[dict[str, PaymentProvider], Depends(get_payment_providers)]


def get_subscription_service(
    session: SessionDep,
    redis: RedisDep,
    settings: SettingsDep,
    providers: ProvidersDep,
) -> SubscriptionService:
    return SubscriptionService(
        session=session,
        providers=providers,
        app_base_url=settings.app_base_url,
        notifications=NotificationService(session, redis),
    )


BillingServiceDep = Annotated[SubscriptionService, Depends(get_subscription_service)]


# -- schemas ---------------------------------------------------------------------


class PlanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    description: str
    price_monthly: Decimal
    price_yearly: Decimal
    currency: str
    features: list[str]
    trial_days: int
    is_active: bool
    sort_order: int


class PlanWithLimitsResponse(PlanResponse):
    limits: dict[str, Any] = Field(default_factory=dict)


class SubscriptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: str
    plan_code: str
    plan_name: str
    billing_cycle: str
    price_monthly: Decimal
    price_yearly: Decimal
    currency: str
    current_period_start: datetime
    current_period_end: datetime
    trial_end: datetime | None
    trial_available: bool
    cancel_at_period_end: bool
    limits: dict[str, Any]
    features: list[str]
    provider: str | None
    provider_status: str | None


class CheckoutRequest(BaseModel):
    plan_code: str = Field(min_length=1, max_length=40)
    cycle: Literal["monthly", "yearly"] = "monthly"
    provider: Literal["razorpay", "stripe"] | None = None
    coupon_code: str | None = Field(default=None, max_length=40)
    use_trial: bool = False


class CheckoutResponse(BaseModel):
    kind: str
    message: str
    invoice_id: UUID | None
    provider: str | None = None
    checkout_url: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class RazorpayConfirmRequest(BaseModel):
    invoice_id: UUID
    order_id: str = Field(min_length=1, max_length=120)
    payment_id: str = Field(min_length=1, max_length=120)
    signature: str = Field(min_length=1, max_length=256)


class CouponPreviewRequest(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    plan_code: str = Field(min_length=1, max_length=40)
    cycle: Literal["monthly", "yearly"] = "monthly"


class CouponPreviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    description: str
    discount: Decimal
    subtotal: Decimal
    total: Decimal
    currency: str


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    number: str
    status: str
    currency: str
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    tax_rate: Decimal
    total: Decimal
    line_items: list[dict[str, Any]]
    period_start: datetime
    period_end: datetime
    coupon_code: str | None
    provider: str | None
    issued_at: datetime
    paid_at: datetime | None


class PaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    invoice_id: UUID
    provider: str
    provider_payment_id: str
    amount: Decimal
    currency: str
    status: str
    method: str | None
    error: str | None
    captured_at: datetime | None
    created_at: datetime


class UsageResponse(BaseModel):
    limits: dict[str, Any]
    usage: dict[str, int]


class MessageResponse(BaseModel):
    message: str


class ProvidersResponse(BaseModel):
    providers: list[str]


# -- routes -----------------------------------------------------------------------


@router.get("/plans", response_model=list[PlanResponse])
async def list_plans(service: BillingServiceDep) -> list[PlanResponse]:
    """Public plan catalog (used by the landing pricing page)."""
    plans = await service.list_plans()
    return [PlanResponse.model_validate(p) for p in plans]


@router.get("/providers", response_model=ProvidersResponse)
async def list_providers(providers: ProvidersDep) -> ProvidersResponse:
    return ProvidersResponse(providers=sorted(providers))


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    tenant: BillingViewTenant, service: BillingServiceDep
) -> SubscriptionResponse:
    summary = await service.get_summary(tenant.organization_id)
    return SubscriptionResponse.model_validate(summary)


@router.post("/checkout", response_model=CheckoutResponse)
async def start_checkout(
    payload: CheckoutRequest,
    request: Request,
    tenant: BillingTenant,
    service: BillingServiceDep,
    session: SessionDep,
) -> CheckoutResponse:
    result = await service.start_checkout(
        tenant.organization_id,
        plan_code=payload.plan_code,
        cycle=BillingCycle(payload.cycle),
        provider_name=payload.provider,
        coupon_code=payload.coupon_code,
        customer_email=tenant.user.email,
        use_trial=payload.use_trial,
    )
    await AuditService(session).record(
        action="billing.checkout_started",
        resource_type="subscription",
        resource_id=str(result.invoice_id or ""),
        organization_id=tenant.organization_id,
        actor_user_id=tenant.user.user_id,
        request_id=getattr(request.state, "request_id", None),
        after_state={"plan": payload.plan_code, "cycle": payload.cycle},
    )
    return CheckoutResponse(
        kind=result.kind,
        message=result.message,
        invoice_id=result.invoice_id,
        provider=result.checkout.provider if result.checkout else None,
        checkout_url=result.checkout.checkout_url if result.checkout else None,
        payload=result.checkout.payload if result.checkout else {},
    )


@router.post("/checkout/razorpay/confirm", response_model=MessageResponse)
async def confirm_razorpay(
    payload: RazorpayConfirmRequest,
    tenant: BillingTenant,
    service: BillingServiceDep,
    providers: ProvidersDep,
) -> MessageResponse:
    provider = providers.get("razorpay")
    if not isinstance(provider, RazorpayProvider):
        raise NotFoundError("razorpay is not configured")
    valid = provider.verify_payment_signature(
        order_id=payload.order_id,
        payment_id=payload.payment_id,
        signature=payload.signature,
    )
    await service.confirm_razorpay_payment(
        tenant.organization_id,
        invoice_id=payload.invoice_id,
        order_id=payload.order_id,
        payment_id=payload.payment_id,
        signature_valid=valid,
    )
    return MessageResponse(message="payment confirmed; plan activated")


@router.post("/coupons/preview", response_model=CouponPreviewResponse)
async def preview_coupon(
    payload: CouponPreviewRequest,
    tenant: BillingViewTenant,
    service: BillingServiceDep,
) -> CouponPreviewResponse:
    preview = await service.preview_coupon(
        code=payload.code,
        plan_code=payload.plan_code,
        cycle=BillingCycle(payload.cycle),
    )
    return CouponPreviewResponse.model_validate(preview)


@router.post("/cancel", response_model=MessageResponse)
async def cancel_subscription(
    request: Request,
    tenant: BillingTenant,
    service: BillingServiceDep,
    session: SessionDep,
) -> MessageResponse:
    await service.cancel_at_period_end(tenant.organization_id)
    await AuditService(session).record(
        action="billing.cancellation_scheduled",
        resource_type="subscription",
        resource_id=str(tenant.organization_id),
        organization_id=tenant.organization_id,
        actor_user_id=tenant.user.user_id,
        request_id=getattr(request.state, "request_id", None),
    )
    return MessageResponse(message="cancellation scheduled for the end of the period")


@router.post("/resume", response_model=MessageResponse)
async def resume_subscription(
    request: Request,
    tenant: BillingTenant,
    service: BillingServiceDep,
    session: SessionDep,
) -> MessageResponse:
    await service.resume(tenant.organization_id)
    await AuditService(session).record(
        action="billing.cancellation_resumed",
        resource_type="subscription",
        resource_id=str(tenant.organization_id),
        organization_id=tenant.organization_id,
        actor_user_id=tenant.user.user_id,
        request_id=getattr(request.state, "request_id", None),
    )
    return MessageResponse(message="subscription will renew normally")


@router.get("/invoices", response_model=list[InvoiceResponse])
async def list_invoices(
    tenant: BillingViewTenant, service: BillingServiceDep, page: PageDep
) -> list[InvoiceResponse]:
    invoices = await service.list_invoices(
        tenant.organization_id, limit=page.limit, offset=page.offset
    )
    return [InvoiceResponse.model_validate(i) for i in invoices]


@router.get("/invoices/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: UUID, tenant: BillingViewTenant, service: BillingServiceDep
) -> InvoiceResponse:
    invoice = await service.get_invoice(tenant.organization_id, invoice_id)
    return InvoiceResponse.model_validate(invoice)


@router.get("/payments", response_model=list[PaymentResponse])
async def list_payments(
    tenant: BillingViewTenant, service: BillingServiceDep, page: PageDep
) -> list[PaymentResponse]:
    payments = await service.list_payments(
        tenant.organization_id, limit=page.limit, offset=page.offset
    )
    return [PaymentResponse.model_validate(p) for p in payments]


@router.get("/usage", response_model=UsageResponse)
async def get_usage(tenant: BillingViewTenant, service: BillingServiceDep) -> UsageResponse:
    limits = await service.current_limits(tenant.organization_id)
    usage = await service.usage_summary(tenant.organization_id)
    return UsageResponse(limits=limits.to_mapping(), usage=usage)


# -- webhooks (provider-authenticated, no user auth) -----------------------------------


webhooks_router = APIRouter(prefix="/billing/webhooks", tags=["billing-webhooks"])


@webhooks_router.post("/razorpay", response_model=MessageResponse)
async def razorpay_webhook(
    request: Request, providers: ProvidersDep, service: BillingServiceDep
) -> MessageResponse:
    provider = providers.get("razorpay")
    if provider is None:
        raise ValidationFailed("razorpay is not configured")
    body = await request.body()
    result = provider.verify_webhook(body=body, headers=dict(request.headers))
    await service.handle_webhook(provider_name="razorpay", result=result)
    return MessageResponse(message="ok")


@webhooks_router.post("/stripe", response_model=MessageResponse)
async def stripe_webhook(
    request: Request, providers: ProvidersDep, service: BillingServiceDep
) -> MessageResponse:
    provider = providers.get("stripe")
    if provider is None:
        raise ValidationFailed("stripe is not configured")
    body = await request.body()
    result = provider.verify_webhook(body=body, headers=dict(request.headers))
    await service.handle_webhook(provider_name="stripe", result=result)
    return MessageResponse(message="ok")
