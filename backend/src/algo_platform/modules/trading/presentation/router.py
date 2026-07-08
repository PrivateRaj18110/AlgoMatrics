from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from algo_platform.api.dependencies.core import (
    RedisDep,
    SessionDep,
    SettingsDep,
)
from algo_platform.api.dependencies.pagination import decode_cursor, encode_cursor
from algo_platform.api.dependencies.tenant import TenantContext, require_permission
from algo_platform.modules.audit.application.service import AuditService
from algo_platform.modules.billing.application.service import SubscriptionService
from algo_platform.modules.billing.presentation.router import ProvidersDep
from algo_platform.modules.notifications.application.service import NotificationService
from algo_platform.modules.organizations.domain.roles import Permission
from algo_platform.modules.risk.application.service import RiskService
from algo_platform.modules.trading.application.order_service import OrderService
from algo_platform.modules.trading.application.queries import TradingQueries
from algo_platform.modules.trading.application.watchlist_service import WatchlistService
from algo_platform.modules.trading.domain.orders import OrderType, TimeInForce
from algo_platform.shared.domain.types import AccountId, OrderId, Side

router = APIRouter(tags=["trading"])

TradingViewTenant = Annotated[TenantContext, Depends(require_permission(Permission.TRADING_VIEW))]
TradingExecuteTenant = Annotated[
    TenantContext, Depends(require_permission(Permission.TRADING_EXECUTE))
]


def get_billing_service(
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


BillingDep = Annotated[SubscriptionService, Depends(get_billing_service)]


def get_order_service(session: SessionDep, redis: RedisDep, billing: BillingDep) -> OrderService:
    return OrderService(session=session, redis=redis, billing=billing, risk=RiskService(session))


def get_trading_queries(session: SessionDep) -> TradingQueries:
    return TradingQueries(session)


def get_watchlist_service(session: SessionDep, billing: BillingDep) -> WatchlistService:
    return WatchlistService(session, billing)


OrderServiceDep = Annotated[OrderService, Depends(get_order_service)]
QueriesDep = Annotated[TradingQueries, Depends(get_trading_queries)]
WatchlistServiceDep = Annotated[WatchlistService, Depends(get_watchlist_service)]


# -- schemas -----------------------------------------------------------------------


class PlaceOrderRequest(BaseModel):
    account_id: UUID
    instrument_id: UUID
    side: Literal["buy", "sell"]
    quantity: Decimal = Field(gt=0)
    order_type: Literal["market", "limit", "stop", "stop_limit"] = "market"
    time_in_force: Literal["day", "gtc", "ioc", "fok"] = "day"
    limit_price: Decimal | None = Field(default=None, gt=0)
    stop_price: Decimal | None = Field(default=None, gt=0)
    client_order_id: str | None = Field(default=None, min_length=1, max_length=64)


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID
    instrument_id: UUID
    symbol: str
    side: str
    order_type: str
    time_in_force: str
    quantity: Decimal
    limit_price: Decimal | None
    stop_price: Decimal | None
    status: str
    filled_quantity: Decimal
    average_fill_price: Decimal | None
    rejection_reason: str | None
    source: str
    client_order_id: str
    strategy_run_id: UUID | None
    created_at: datetime
    updated_at: datetime


class PlacedOrderResponse(BaseModel):
    id: UUID
    status: str
    client_order_id: str
    rejection_reason: str | None


class TradeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    account_id: UUID
    instrument_id: UUID
    symbol: str
    side: str
    quantity: Decimal
    price: Decimal
    fee: Decimal
    fee_currency: str
    executed_at: datetime


class OrderDetailResponse(BaseModel):
    order: OrderResponse
    executions: list[TradeResponse]


class PositionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID
    instrument_id: UUID
    symbol: str
    side: str
    quantity: Decimal
    average_price: Decimal
    last_mark: Decimal | None
    market_value: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    fees_paid: Decimal
    updated_at: datetime


class PagedOrdersResponse(BaseModel):
    items: list[OrderResponse]
    next_cursor: str | None


class PagedTradesResponse(BaseModel):
    items: list[TradeResponse]
    next_cursor: str | None


class WatchlistItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    instrument_id: UUID
    symbol: str
    name: str
    sort_order: int


class WatchlistResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime
    items: list[WatchlistItemResponse]


class CreateWatchlistRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class AddWatchlistItemRequest(BaseModel):
    instrument_id: UUID


class MessageResponse(BaseModel):
    message: str


# -- orders ------------------------------------------------------------------------


@router.post("/orders", response_model=PlacedOrderResponse, status_code=status.HTTP_201_CREATED)
async def place_order(
    payload: PlaceOrderRequest,
    request: Request,
    tenant: TradingExecuteTenant,
    service: OrderServiceDep,
    session: SessionDep,
) -> PlacedOrderResponse:
    order = await service.place_order(
        tenant.organization_id,
        account_id=AccountId(payload.account_id),
        instrument_id=payload.instrument_id,
        side=Side(payload.side),
        quantity=payload.quantity,
        order_type=OrderType(payload.order_type),
        time_in_force=TimeInForce(payload.time_in_force),
        limit_price=payload.limit_price,
        stop_price=payload.stop_price,
        client_order_id=payload.client_order_id,
        source="manual",
    )
    await AuditService(session).record(
        action="trading.order_placed",
        resource_type="order",
        resource_id=str(order.id),
        organization_id=tenant.organization_id,
        actor_user_id=tenant.user.user_id,
        request_id=getattr(request.state, "request_id", None),
        after_state={
            "side": payload.side,
            "quantity": str(payload.quantity),
            "status": order.status.value,
        },
    )
    return PlacedOrderResponse(
        id=order.id,
        status=order.status.value,
        client_order_id=order.intent.client_order_id,
        rejection_reason=order.rejection_reason,
    )


@router.get("/orders", response_model=PagedOrdersResponse)
async def list_orders(
    tenant: TradingViewTenant,
    queries: QueriesDep,
    account_id: Annotated[UUID | None, Query()] = None,
    order_status: Annotated[str | None, Query(alias="status", max_length=20)] = None,
    instrument_id: Annotated[UUID | None, Query()] = None,
    open_only: Annotated[bool, Query()] = False,
    cursor: Annotated[str | None, Query(max_length=400)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PagedOrdersResponse:
    parsed_cursor = decode_cursor(cursor) if cursor else None
    items = await queries.list_orders(
        tenant.organization_id,
        account_id=account_id,
        status=order_status,
        instrument_id=instrument_id,
        cursor=parsed_cursor,
        limit=limit,
        open_only=open_only,
    )
    next_cursor = encode_cursor(items[-1].created_at, items[-1].id) if len(items) == limit else None
    return PagedOrdersResponse(
        items=[OrderResponse.model_validate(i) for i in items], next_cursor=next_cursor
    )


@router.get("/orders/{order_id}", response_model=OrderDetailResponse)
async def get_order(
    order_id: UUID, tenant: TradingViewTenant, queries: QueriesDep
) -> OrderDetailResponse:
    found = await queries.get_order(tenant.organization_id, order_id)
    if found is None:
        from algo_platform.shared.domain.errors import NotFoundError

        raise NotFoundError("order not found")
    order, executions = found
    return OrderDetailResponse(
        order=OrderResponse.model_validate(order),
        executions=[TradeResponse.model_validate(e) for e in executions],
    )


@router.post("/orders/{order_id}/cancel", response_model=PlacedOrderResponse)
async def cancel_order(
    order_id: UUID,
    request: Request,
    tenant: TradingExecuteTenant,
    service: OrderServiceDep,
    session: SessionDep,
) -> PlacedOrderResponse:
    order = await service.cancel_order(tenant.organization_id, OrderId(order_id))
    await AuditService(session).record(
        action="trading.order_cancel_requested",
        resource_type="order",
        resource_id=str(order.id),
        organization_id=tenant.organization_id,
        actor_user_id=tenant.user.user_id,
        request_id=getattr(request.state, "request_id", None),
    )
    return PlacedOrderResponse(
        id=order.id,
        status=order.status.value,
        client_order_id=order.intent.client_order_id,
        rejection_reason=order.rejection_reason,
    )


# -- trades / positions ---------------------------------------------------------------


@router.get("/trades", response_model=PagedTradesResponse)
async def list_trades(
    tenant: TradingViewTenant,
    queries: QueriesDep,
    account_id: Annotated[UUID | None, Query()] = None,
    instrument_id: Annotated[UUID | None, Query()] = None,
    cursor: Annotated[str | None, Query(max_length=400)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PagedTradesResponse:
    parsed_cursor = decode_cursor(cursor) if cursor else None
    items = await queries.list_trades(
        tenant.organization_id,
        account_id=account_id,
        instrument_id=instrument_id,
        cursor=parsed_cursor,
        limit=limit,
    )
    next_cursor = (
        encode_cursor(items[-1].executed_at, items[-1].id) if len(items) == limit else None
    )
    return PagedTradesResponse(
        items=[TradeResponse.model_validate(i) for i in items], next_cursor=next_cursor
    )


@router.get("/positions", response_model=list[PositionResponse])
async def list_positions(
    tenant: TradingViewTenant,
    queries: QueriesDep,
    account_id: Annotated[UUID | None, Query()] = None,
    include_closed: Annotated[bool, Query()] = False,
) -> list[PositionResponse]:
    items = await queries.list_positions(
        tenant.organization_id, account_id=account_id, open_only=not include_closed
    )
    return [PositionResponse.model_validate(i) for i in items]


# -- watchlists ------------------------------------------------------------------------


@router.get("/watchlists", response_model=list[WatchlistResponse])
async def list_watchlists(
    tenant: TradingViewTenant, service: WatchlistServiceDep
) -> list[WatchlistResponse]:
    watchlists = await service.list(tenant.organization_id)
    return [WatchlistResponse.model_validate(w) for w in watchlists]


@router.post("/watchlists", response_model=WatchlistResponse, status_code=status.HTTP_201_CREATED)
async def create_watchlist(
    payload: CreateWatchlistRequest,
    tenant: TradingViewTenant,
    service: WatchlistServiceDep,
) -> WatchlistResponse:
    watchlist = await service.create(
        tenant.organization_id, name=payload.name, created_by=tenant.user.user_id
    )
    return WatchlistResponse.model_validate(watchlist)


@router.patch("/watchlists/{watchlist_id}", response_model=WatchlistResponse)
async def rename_watchlist(
    watchlist_id: UUID,
    payload: CreateWatchlistRequest,
    tenant: TradingViewTenant,
    service: WatchlistServiceDep,
) -> WatchlistResponse:
    watchlist = await service.rename(tenant.organization_id, watchlist_id, name=payload.name)
    return WatchlistResponse.model_validate(watchlist)


@router.delete("/watchlists/{watchlist_id}", response_model=MessageResponse)
async def delete_watchlist(
    watchlist_id: UUID, tenant: TradingViewTenant, service: WatchlistServiceDep
) -> MessageResponse:
    await service.remove(tenant.organization_id, watchlist_id)
    return MessageResponse(message="watchlist removed")


@router.post("/watchlists/{watchlist_id}/items", response_model=WatchlistResponse)
async def add_watchlist_item(
    watchlist_id: UUID,
    payload: AddWatchlistItemRequest,
    tenant: TradingViewTenant,
    service: WatchlistServiceDep,
) -> WatchlistResponse:
    watchlist = await service.add_item(
        tenant.organization_id, watchlist_id, instrument_id=payload.instrument_id
    )
    return WatchlistResponse.model_validate(watchlist)


@router.delete("/watchlists/{watchlist_id}/items/{item_id}", response_model=WatchlistResponse)
async def remove_watchlist_item(
    watchlist_id: UUID,
    item_id: UUID,
    tenant: TradingViewTenant,
    service: WatchlistServiceDep,
) -> WatchlistResponse:
    watchlist = await service.remove_item(tenant.organization_id, watchlist_id, item_id=item_id)
    return WatchlistResponse.model_validate(watchlist)
