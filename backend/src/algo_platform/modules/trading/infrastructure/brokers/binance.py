"""Binance Spot execution adapter (REST, HMAC-SHA256 signed).

Signature: hex HMAC-SHA256 over the exact request query string with the API
secret, sent as the ``signature`` parameter; the API key travels in the
``X-MBX-APIKEY`` header. https://binance-docs.github.io/apidocs/spot/en/
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from decimal import Decimal
from urllib.parse import urlencode
from uuid import UUID

import httpx
import structlog

from algo_platform.modules.trading.application.broker_port import (
    BrokerOrderAck,
    BrokerOrderUpdate,
)
from algo_platform.modules.trading.domain.orders import OrderIntent, OrderStatus, OrderType
from algo_platform.modules.trading.infrastructure.brokers.indian import VenueInstrument
from algo_platform.shared.domain.errors import ConflictError
from algo_platform.shared.domain.types import utc_now

logger = structlog.get_logger(__name__)

_BASE = "https://api.binance.com"
_TIMEOUT = httpx.Timeout(15.0)
_POLL_SECONDS = 2.0
_RECV_WINDOW = 5_000

SymbolResolver = Callable[[UUID], Awaitable[VenueInstrument]]

_BINANCE_STATUS_MAP = {
    "NEW": "submitted",
    "PARTIALLY_FILLED": "partially_filled",
    "FILLED": "filled",
    "CANCELED": "cancelled",
    "PENDING_CANCEL": "cancel_pending",
    "REJECTED": "rejected",
    "EXPIRED": "cancelled",
}


class BinanceExecutionAdapter:
    def __init__(self, *, api_key: str, api_secret: str, symbol_resolver: SymbolResolver) -> None:
        self._api_key = api_key
        self._api_secret = api_secret.encode("utf-8")
        self._resolve = symbol_resolver
        self._client: httpx.AsyncClient | None = None
        self._tracked: dict[str, str] = {}
        self._symbols: dict[str, str] = {}
        self._running = False

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(base_url=_BASE, timeout=_TIMEOUT)
        self._running = True

    async def disconnect(self) -> None:
        self._running = False
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise ConflictError("Binance adapter is not connected")
        return self._client

    def _sign(self, params: dict[str, object]) -> str:
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = _RECV_WINDOW
        query = urlencode(params)
        signature = hmac.new(self._api_secret, query.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{query}&signature={signature}"

    @property
    def _headers(self) -> dict[str, str]:
        return {"X-MBX-APIKEY": self._api_key}

    async def health(self) -> bool:
        client = self._require_client()
        try:
            response = await client.get("/api/v3/ping")
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    async def _symbol(self, instrument_id: UUID) -> str:
        venue = await self._resolve(instrument_id)
        self._symbols[venue.symbol] = venue.symbol
        return venue.symbol

    async def submit_order(self, intent: OrderIntent) -> BrokerOrderAck:
        client = self._require_client()
        symbol = await self._symbol(intent.instrument_id)
        params: dict[str, object] = {
            "symbol": symbol,
            "side": intent.side.value.upper(),
            "type": _binance_type(intent.order_type),
            "quantity": str(intent.quantity),
            "newClientOrderId": intent.client_order_id,
        }
        if intent.order_type in {OrderType.LIMIT, OrderType.STOP_LIMIT}:
            params["price"] = str(intent.limit_price)
            params["timeInForce"] = "IOC" if intent.time_in_force.value == "ioc" else "GTC"
        if intent.order_type in {OrderType.STOP, OrderType.STOP_LIMIT}:
            params["stopPrice"] = str(intent.stop_price)
        response = await client.post(
            f"/api/v3/order?{self._sign(params)}", headers=self._headers
        )
        if response.status_code >= 400:
            detail = str(response.json().get("msg", f"HTTP {response.status_code}"))
            raise ConflictError(f"Binance rejected the order: {detail}")
        broker_order_id = str(response.json()["orderId"])
        self._tracked[broker_order_id] = intent.client_order_id
        return BrokerOrderAck(
            broker_order_id=broker_order_id,
            client_order_id=intent.client_order_id,
            status=OrderStatus.SUBMITTED,
            accepted_at=utc_now(),
        )

    async def cancel_order(self, broker_order_id: str) -> BrokerOrderAck:
        client = self._require_client()
        symbol = next(iter(self._symbols), "")
        params: dict[str, object] = {"symbol": symbol, "orderId": broker_order_id}
        response = await client.delete(
            f"/api/v3/order?{self._sign(params)}", headers=self._headers
        )
        if response.status_code >= 400:
            detail = str(response.json().get("msg", f"HTTP {response.status_code}"))
            raise ConflictError(f"Binance cancel failed: {detail}")
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
        # Spot has no in-place amend; atomically cancel and re-place.
        client = self._require_client()
        symbol = next(iter(self._symbols), "")
        params: dict[str, object] = {
            "symbol": symbol,
            "cancelReplaceMode": "STOP_ON_FAILURE",
            "cancelOrderId": broker_order_id,
            "side": "BUY",
            "type": "LIMIT",
            "timeInForce": "GTC",
        }
        if quantity is not None:
            params["quantity"] = str(quantity)
        if limit_price is not None:
            params["price"] = str(limit_price)
        if stop_price is not None:
            params["stopPrice"] = str(stop_price)
        response = await client.post(
            f"/api/v3/order/cancelReplace?{self._sign(params)}", headers=self._headers
        )
        if response.status_code >= 400:
            detail = str(response.json().get("msg", f"HTTP {response.status_code}"))
            raise ConflictError(f"Binance replace failed: {detail}")
        new_order = response.json().get("newOrderResponse", {})
        new_id = str(new_order.get("orderId", broker_order_id))
        self._tracked[new_id] = self._tracked.get(broker_order_id, "")
        return BrokerOrderAck(
            broker_order_id=new_id,
            client_order_id=self._tracked.get(new_id, ""),
            status=OrderStatus.SUBMITTED,
            accepted_at=utc_now(),
        )

    async def stream_order_updates(self) -> AsyncIterator[BrokerOrderUpdate]:
        seen_state: dict[str, tuple[str, str]] = {}
        while self._running:
            client = self._require_client()
            symbol = next(iter(self._symbols), "")
            if not symbol:
                await asyncio.sleep(_POLL_SECONDS)
                continue
            try:
                response = await client.get(
                    f"/api/v3/openOrders?{self._sign({'symbol': symbol})}",
                    headers=self._headers,
                )
            except httpx.HTTPError as error:
                logger.warning("binance.poll_failed", error=type(error).__name__)
                await asyncio.sleep(_POLL_SECONDS * 2)
                continue
            if response.status_code == 200:
                for raw in response.json():
                    update = self._to_update(raw, seen_state)
                    if update is not None:
                        yield update
            await asyncio.sleep(_POLL_SECONDS)

    def _to_update(
        self, raw: dict[str, object], seen_state: dict[str, tuple[str, str]]
    ) -> BrokerOrderUpdate | None:
        broker_order_id = str(raw.get("orderId", ""))
        if broker_order_id not in self._tracked:
            return None
        status_raw = str(raw.get("status", "")).upper()
        filled = Decimal(str(raw.get("executedQty", 0) or 0))
        fingerprint = (status_raw, str(filled))
        if seen_state.get(broker_order_id) == fingerprint:
            return None
        seen_state[broker_order_id] = fingerprint
        mapped = _BINANCE_STATUS_MAP.get(status_raw)
        if mapped is None:
            return None
        quote = Decimal(str(raw.get("cummulativeQuoteQty", 0) or 0))
        average = (quote / filled) if filled > 0 else None
        return BrokerOrderUpdate(
            broker_order_id=broker_order_id,
            client_order_id=self._tracked[broker_order_id],
            status=OrderStatus(mapped),
            filled_quantity=filled,
            average_price=average,
            occurred_at=utc_now(),
            raw_reference=status_raw,
        )

    async def get_balances(self) -> dict[str, Decimal]:
        client = self._require_client()
        response = await client.get(
            f"/api/v3/account?{self._sign({})}", headers=self._headers
        )
        if response.status_code != 200:
            return {}
        balances: dict[str, Decimal] = {}
        for entry in response.json().get("balances", []):
            free = Decimal(str(entry.get("free", 0)))
            if free > 0:
                balances[str(entry.get("asset", ""))] = free
        return balances

    async def get_positions(self) -> list[dict[str, object]]:
        # Spot has no positions concept; holdings are surfaced via balances.
        return []


def _binance_type(order_type: OrderType) -> str:
    return {
        OrderType.MARKET: "MARKET",
        OrderType.LIMIT: "LIMIT",
        OrderType.STOP: "STOP_LOSS",
        OrderType.STOP_LIMIT: "STOP_LOSS_LIMIT",
    }.get(order_type, "LIMIT")
