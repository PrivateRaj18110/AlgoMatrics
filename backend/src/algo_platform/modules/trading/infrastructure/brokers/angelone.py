"""Angel One SmartAPI execution adapter (REST).

Implements ``BrokerExecutionPort`` against https://apiconnect.angelone.in.
Order updates come from polling the order book endpoint.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from decimal import Decimal
from uuid import UUID

import httpx
import structlog

from algo_platform.modules.trading.application.broker_port import (
    BrokerOrderAck,
    BrokerOrderUpdate,
)
from algo_platform.modules.trading.domain.orders import OrderIntent, OrderStatus, OrderType
from algo_platform.modules.trading.infrastructure.brokers.indian import (
    VenueInstrument,
    ensure_lot_multiple,
    to_nse_transaction_type,
    to_nse_validity,
)
from algo_platform.shared.domain.errors import ConflictError
from algo_platform.shared.domain.types import utc_now

logger = structlog.get_logger(__name__)

_BASE = "https://apiconnect.angelone.in"
_TIMEOUT = httpx.Timeout(15.0)
_POLL_SECONDS = 2.0

SymbolResolver = Callable[[UUID], Awaitable[VenueInstrument]]

_SMART_ORDER_TYPE = {
    OrderType.MARKET: "MARKET",
    OrderType.LIMIT: "LIMIT",
    OrderType.STOP: "STOPLOSS_MARKET",
    OrderType.STOP_LIMIT: "STOPLOSS_LIMIT",
}

_SMART_STATUS_MAP = {
    "open": "submitted",
    "trigger pending": "submitted",
    "pending": "submitted",
    "validation pending": "submitted",
    "open pending": "submitted",
    "modified": "submitted",
    "complete": "filled",
    "cancelled": "cancelled",
    "rejected": "rejected",
}


class AngelOneExecutionAdapter:
    def __init__(
        self,
        *,
        api_key: str,
        jwt_token: str,
        client_code: str,
        symbol_resolver: SymbolResolver,
        product: str = "INTRADAY",
    ) -> None:
        self._headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": "127.0.0.1",
            "X-ClientPublicIP": "127.0.0.1",
            "X-MACAddress": "00:00:00:00:00:00",
            "X-PrivateKey": api_key,
        }
        self._client_code = client_code
        self._resolve = symbol_resolver
        self._product = product
        self._client: httpx.AsyncClient | None = None
        self._tracked: dict[str, str] = {}
        self._running = False

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(base_url=_BASE, headers=self._headers, timeout=_TIMEOUT)
        self._running = True

    async def disconnect(self) -> None:
        self._running = False
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise ConflictError("Angel One adapter is not connected")
        return self._client

    async def health(self) -> bool:
        client = self._require_client()
        try:
            response = await client.get("/rest/secure/angelbroking/user/v1/getProfile")
        except httpx.HTTPError:
            return False
        return response.status_code == 200 and bool(response.json().get("status"))

    async def submit_order(self, intent: OrderIntent) -> BrokerOrderAck:
        client = self._require_client()
        venue = await self._resolve(intent.instrument_id)
        quantity = ensure_lot_multiple(intent.quantity, venue.lot_size, venue.symbol)
        payload: dict[str, str] = {
            "variety": "NORMAL"
            if intent.order_type in {OrderType.MARKET, OrderType.LIMIT}
            else "STOPLOSS",
            "tradingsymbol": venue.symbol,
            "symboltoken": venue.token,
            "transactiontype": to_nse_transaction_type(intent.side.value),
            "exchange": venue.exchange or "NSE",
            "ordertype": _SMART_ORDER_TYPE[intent.order_type],
            "producttype": self._product,
            "duration": to_nse_validity(intent.time_in_force),
            "quantity": str(quantity),
            "ordertag": intent.client_order_id[:20],
        }
        if intent.limit_price is not None:
            payload["price"] = str(intent.limit_price)
        if intent.stop_price is not None:
            payload["triggerprice"] = str(intent.stop_price)
        response = await client.post("/rest/secure/angelbroking/order/v1/placeOrder", json=payload)
        body = response.json() if response.status_code < 500 else {}
        if response.status_code >= 400 or not body.get("status"):
            detail = str(body.get("message", f"HTTP {response.status_code}"))
            raise ConflictError(f"SmartAPI rejected the order: {detail}")
        broker_order_id = str(body.get("data", {}).get("orderid", ""))
        self._tracked[broker_order_id] = intent.client_order_id
        return BrokerOrderAck(
            broker_order_id=broker_order_id,
            client_order_id=intent.client_order_id,
            status=OrderStatus.SUBMITTED,
            accepted_at=utc_now(),
        )

    async def cancel_order(self, broker_order_id: str) -> BrokerOrderAck:
        client = self._require_client()
        response = await client.post(
            "/rest/secure/angelbroking/order/v1/cancelOrder",
            json={"variety": "NORMAL", "orderid": broker_order_id},
        )
        body = response.json() if response.status_code < 500 else {}
        if response.status_code >= 400 or not body.get("status"):
            detail = str(body.get("message", f"HTTP {response.status_code}"))
            raise ConflictError(f"SmartAPI cancel failed: {detail}")
        return BrokerOrderAck(
            broker_order_id=broker_order_id,
            client_order_id=self._tracked.get(broker_order_id, ""),
            status=OrderStatus.CANCEL_PENDING,
            accepted_at=utc_now(),
        )

    async def replace_order(
        self,
        broker_order_id: str,
        *,
        quantity: Decimal | None = None,
        limit_price: Decimal | None = None,
        stop_price: Decimal | None = None,
    ) -> BrokerOrderAck:
        client = self._require_client()
        payload: dict[str, str] = {"variety": "NORMAL", "orderid": broker_order_id}
        if quantity is not None:
            payload["quantity"] = str(int(quantity))
        if limit_price is not None:
            payload["price"] = str(limit_price)
        if stop_price is not None:
            payload["triggerprice"] = str(stop_price)
        response = await client.post("/rest/secure/angelbroking/order/v1/modifyOrder", json=payload)
        body = response.json() if response.status_code < 500 else {}
        if response.status_code >= 400 or not body.get("status"):
            detail = str(body.get("message", f"HTTP {response.status_code}"))
            raise ConflictError(f"SmartAPI modify failed: {detail}")
        return BrokerOrderAck(
            broker_order_id=broker_order_id,
            client_order_id=self._tracked.get(broker_order_id, ""),
            status=OrderStatus.SUBMITTED,
            accepted_at=utc_now(),
        )

    async def stream_order_updates(self) -> AsyncIterator[BrokerOrderUpdate]:
        seen_state: dict[str, tuple[str, str]] = {}
        while self._running:
            client = self._require_client()
            try:
                response = await client.get("/rest/secure/angelbroking/order/v1/getOrderBook")
            except httpx.HTTPError as error:
                logger.warning("angelone.poll_failed", error=type(error).__name__)
                await asyncio.sleep(_POLL_SECONDS * 2)
                continue
            if response.status_code == 200 and response.json().get("status"):
                for raw in response.json().get("data") or []:
                    broker_order_id = str(raw.get("orderid", ""))
                    if broker_order_id not in self._tracked:
                        continue
                    status_raw = str(raw.get("status", "")).lower()
                    filled = Decimal(str(raw.get("filledshares", 0) or 0))
                    fingerprint = (status_raw, str(filled))
                    if seen_state.get(broker_order_id) == fingerprint:
                        continue
                    seen_state[broker_order_id] = fingerprint
                    mapped = _SMART_STATUS_MAP.get(status_raw)
                    if mapped is None:
                        continue
                    average = raw.get("averageprice")
                    yield BrokerOrderUpdate(
                        broker_order_id=broker_order_id,
                        client_order_id=self._tracked[broker_order_id],
                        status=OrderStatus(mapped),
                        filled_quantity=filled,
                        average_price=Decimal(str(average)) if average else None,
                        occurred_at=utc_now(),
                        raw_reference=status_raw,
                    )
            await asyncio.sleep(_POLL_SECONDS)

    async def get_balances(self) -> dict[str, Decimal]:
        client = self._require_client()
        response = await client.get("/rest/secure/angelbroking/user/v1/getRMS")
        if response.status_code != 200 or not response.json().get("status"):
            return {}
        data = response.json().get("data") or {}
        return {"cash": Decimal(str(data.get("availablecash", 0) or 0))}

    async def get_positions(self) -> list[dict[str, object]]:
        client = self._require_client()
        response = await client.get("/rest/secure/angelbroking/order/v1/getPosition")
        if response.status_code != 200 or not response.json().get("status"):
            return []
        return [dict(item) for item in response.json().get("data") or []]
