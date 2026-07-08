from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field

from algo_platform.api.dependencies.core import (
    CipherDep,
    RedisDep,
    SessionDep,
    SettingsDep,
)
from algo_platform.api.dependencies.tenant import TenantContext, require_permission
from algo_platform.modules.audit.application.service import AuditService
from algo_platform.modules.billing.application.service import SubscriptionService
from algo_platform.modules.billing.presentation.router import ProvidersDep
from algo_platform.modules.brokerage.application.service import BrokerageService
from algo_platform.modules.brokerage.infrastructure.repositories import (
    SqlBrokerCatalogRepository,
    SqlBrokerConnectionRepository,
    SqlTradingAccountRepository,
)
from algo_platform.modules.brokerage.infrastructure.verifiers import build_verifier_registry
from algo_platform.modules.notifications.application.service import NotificationService
from algo_platform.modules.organizations.domain.roles import Permission
from algo_platform.shared.domain.types import AccountId

router = APIRouter(tags=["brokers"])

BrokersViewTenant = Annotated[TenantContext, Depends(require_permission(Permission.BROKERS_VIEW))]
BrokersManageTenant = Annotated[
    TenantContext, Depends(require_permission(Permission.BROKERS_MANAGE))
]


def get_brokerage_service(
    session: SessionDep,
    cipher: CipherDep,
    redis: RedisDep,
    settings: SettingsDep,
    providers: ProvidersDep,
) -> BrokerageService:
    billing = SubscriptionService(
        session=session,
        providers=providers,
        app_base_url=settings.app_base_url,
        notifications=NotificationService(session, redis),
    )
    return BrokerageService(
        catalog=SqlBrokerCatalogRepository(session),
        connections=SqlBrokerConnectionRepository(session),
        accounts=SqlTradingAccountRepository(session),
        verifiers=build_verifier_registry(
            mt5_allowed_hosts=settings.mt5_agent_allowed_hosts,
            mt5_require_https=settings.app_env not in {"local", "test"},
        ),
        cipher=cipher,
        billing=billing,
    )


BrokerageServiceDep = Annotated[BrokerageService, Depends(get_brokerage_service)]


class BrokerCatalogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    description: str
    credential_fields: list[dict[str, Any]]
    capabilities: dict[str, Any]
    supports_paper: bool
    supports_live: bool


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    connection_id: UUID
    external_account_id: str
    name: str
    mode: str
    base_currency: str
    cash_balance: Decimal
    starting_balance: Decimal
    equity: Decimal
    status: str


class ConnectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    broker_code: str
    broker_name: str
    name: str
    status: str
    last_verified_at: datetime | None
    failure_reason: str | None
    created_at: datetime
    accounts: list[AccountResponse]


class AddConnectionRequest(BaseModel):
    broker_code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=120)
    credentials: dict[str, str]
    account_mode: Literal["paper", "live"] = "paper"


class UpdateConnectionRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    credentials: dict[str, str] | None = None


class MessageResponse(BaseModel):
    message: str


@router.get("/brokers", response_model=list[BrokerCatalogResponse])
async def list_brokers(
    tenant: BrokersViewTenant, service: BrokerageServiceDep
) -> list[BrokerCatalogResponse]:
    brokers = await service.list_brokers()
    return [BrokerCatalogResponse.model_validate(b) for b in brokers]


@router.get("/broker-connections", response_model=list[ConnectionResponse])
async def list_connections(
    tenant: BrokersViewTenant, service: BrokerageServiceDep
) -> list[ConnectionResponse]:
    connections = await service.list_connections(tenant.organization_id)
    return [ConnectionResponse.model_validate(c) for c in connections]


@router.get("/broker-connections/{connection_id}", response_model=ConnectionResponse)
async def get_connection(
    connection_id: UUID, tenant: BrokersViewTenant, service: BrokerageServiceDep
) -> ConnectionResponse:
    connection = await service.get_connection(tenant.organization_id, connection_id)
    return ConnectionResponse.model_validate(connection)


@router.post(
    "/broker-connections",
    response_model=ConnectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_connection(
    payload: AddConnectionRequest,
    request: Request,
    tenant: BrokersManageTenant,
    service: BrokerageServiceDep,
    session: SessionDep,
) -> ConnectionResponse:
    connection = await service.add_connection(
        tenant.organization_id,
        broker_code=payload.broker_code,
        name=payload.name,
        credentials=payload.credentials,
        created_by=tenant.user.user_id,
        account_mode=payload.account_mode,
    )
    await AuditService(session).record(
        action="brokers.connection_added",
        resource_type="broker_connection",
        resource_id=str(connection.id),
        organization_id=tenant.organization_id,
        actor_user_id=tenant.user.user_id,
        request_id=getattr(request.state, "request_id", None),
        after_state={"broker": payload.broker_code, "name": payload.name},
    )
    return ConnectionResponse.model_validate(connection)


@router.patch("/broker-connections/{connection_id}", response_model=ConnectionResponse)
async def update_connection(
    connection_id: UUID,
    payload: UpdateConnectionRequest,
    request: Request,
    tenant: BrokersManageTenant,
    service: BrokerageServiceDep,
    session: SessionDep,
) -> ConnectionResponse:
    connection = await service.update_connection(
        tenant.organization_id,
        connection_id,
        name=payload.name,
        credentials=payload.credentials,
    )
    await AuditService(session).record(
        action="brokers.connection_updated",
        resource_type="broker_connection",
        resource_id=str(connection_id),
        organization_id=tenant.organization_id,
        actor_user_id=tenant.user.user_id,
        request_id=getattr(request.state, "request_id", None),
        after_state={"credentials_rotated": payload.credentials is not None},
    )
    return ConnectionResponse.model_validate(connection)


@router.post("/broker-connections/{connection_id}/verify", response_model=ConnectionResponse)
async def verify_connection(
    connection_id: UUID,
    tenant: BrokersManageTenant,
    service: BrokerageServiceDep,
) -> ConnectionResponse:
    connection = await service.verify_connection(tenant.organization_id, connection_id)
    return ConnectionResponse.model_validate(connection)


@router.delete("/broker-connections/{connection_id}", response_model=MessageResponse)
async def remove_connection(
    connection_id: UUID,
    request: Request,
    tenant: BrokersManageTenant,
    service: BrokerageServiceDep,
    session: SessionDep,
) -> MessageResponse:
    await service.remove_connection(tenant.organization_id, connection_id)
    await AuditService(session).record(
        action="brokers.connection_removed",
        resource_type="broker_connection",
        resource_id=str(connection_id),
        organization_id=tenant.organization_id,
        actor_user_id=tenant.user.user_id,
        request_id=getattr(request.state, "request_id", None),
    )
    return MessageResponse(message="broker connection removed")


@router.get("/accounts", response_model=list[AccountResponse])
async def list_accounts(
    tenant: BrokersViewTenant, service: BrokerageServiceDep
) -> list[AccountResponse]:
    accounts = await service.list_accounts(tenant.organization_id)
    return [AccountResponse.model_validate(a) for a in accounts]


@router.get("/accounts/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: UUID, tenant: BrokersViewTenant, service: BrokerageServiceDep
) -> AccountResponse:
    account = await service.get_account(tenant.organization_id, AccountId(account_id))
    return AccountResponse.model_validate(account)
