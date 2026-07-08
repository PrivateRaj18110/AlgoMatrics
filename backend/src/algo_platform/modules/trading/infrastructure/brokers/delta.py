"""Delta Exchange execution adapter (REST v2, HMAC-signed).

Signature: hex HMAC-SHA256 over ``method + timestamp + path + query + body``
with the API secret. https://docs.delta.exchange
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
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
from algo_platform.modules.trading.infrastructure.brokers.indian import VenueInstrument
from algo_platform.shared.domain.errors import ConflictError, ValidationFailed
from algo_platform.shared.domain.types import utc_now

logger = structlog.get_logger(__name__)

_BASE = "https://api.india.delta.exchange"
_TIMEOUT = httpx.Timeout(15.0)
_POLL_SECONDS = 2.0

SymbolResolver = Callable[[UUID], Awaitable[VenueInstrument]]

_DELTA_STATUS_MAP = {
    "open": "submitted",
    "pending": "submitted",
    "closed": "filled",
    "cancelled": "cancelled",
}


class DeltaExecutionAdapter:
    def __init__(self, *, api_key: str, api_secret: str, symbol_resolver: SymbolResolver) -> None:
        self._api_key = api_key
        self._api_secret = api_secret.encode("utf-8")
        self._resolve = symbol_resolver
        self._client: httpx.AsyncClient | None = None
        self._tracked: dict[str, str] = {}
        self._product_ids: dict[str, int] = {}
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
            raise ConflictError("Delta adapter is not connected")
        return self._client

    def _signed_headers(
        self, method: str, path: str, query: str = "", body: str = ""
    ) -> dict[str, str]:
        timestamp = str(int(time.time()))
        payload = f"{method}{timestamp}{path}{query}{body}"
        signature = hmac.new(self._api_secret, payload.encode("utf-8"), hashlib.sha256)
        return {
            "api-key": self._api_key,
            "timestamp": timestamp,
            "signature": signature.hexdigest(),
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def health(self) -> bool:
        client = self._require_client()
        try:
            response = await client.get(
                "/v2/profile", headers=self._signed_headers("GET", "/v2/profile")
            )
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    async def _product_id(self, symbol: str) -> int:
        if symbol in self._product_ids:
            return self._product_ids[symbol]
        client = self._require_client()
        response = await client.get(f"/v2/products/{symbol}")
        if response.status_code != 200:
            raise ValidationFailed(f"Delta product '{symbol}' not found")
        product_id = int(response.json()["result"]["id"])
        self._product_ids[symbol] = product_id
        return product_id

    async def submit_order(self, intent: OrderIntent) -> BrokerOrderAck:
        client = self._require_client()
        venue = await self._resolve(intent.instrument_id)
        product_id = await self._product_id(venue.symbol)
        payload: dict[str, object] = {
            "product_id": product_id,
            "size": int(intent.quantity),
            "side": intent.side.value,
            "order_type": "market_order"
            if intent.order_type is OrderType.MARKET
            else "limit_order",
            "time_in_force": "ioc" if intent.time_in_force.value == "ioc" else "gtc",
            "client_order_id": intent.client_order_id,
        }
        if intent.order_type in {OrderType.LIMIT, OrderType.STOP_LIMIT}:
            payload["limit_price"] = str(intent.limit_price)
        if intent.order_type in {OrderType.STOP, OrderType.STOP_LIMIT}:
            payload["stop_order_type"] = "stop_loss_order"
            payload["stop_price"] = str(intent.stop_price)
        body = json.dumps(payload, separators=(",", ":"))
        response = await client.post(
            "/v2/orders",
            content=body,
            headers=self._signed_headers("POST", "/v2/orders", body=body),
        )
        if response.status_code >= 400:
            detail = str(response.json().get("error", f"HTTP {response.status_code}"))
            raise ConflictError(f"Delta rejected the order: {detail}")
        broker_order_id = str(response.json()["result"]["id"])
        self._tracked[broker_order_id] = intent.client_order_id
        return BrokerOrderAck(
            broker_order_id=broker_order_id,
            client_order_id=intent.client_order_id,
            status=OrderStatus.SUBMITTED,
            accepted_at=utc_now(),
        )

    async def cancel_order(self, broker_order_id: str) -> BrokerOrderAck:
        client = self._require_client()
        path = f"/v2/orders/{broker_order_id}"
        response = await client.delete(path, headers=self._signed_headers("DELETE", path))
        if response.status_code >= 400:
            detail = str(response.json().get("error", f"HTTP {response.status_code}"))
            raise ConflictError(f"Delta cancel failed: {detail}")
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
        payload: dict[str, object] = {"id": int(broker_order_id)}
        if quantity is not None:
            payload["size"] = int(quantity)
        if limit_price is not None:
            payload["limit_price"] = str(limit_price)
        if stop_price is not None:
            payload["stop_price"] = str(stop_price)
        body = json.dumps(payload, separators=(",", ":"))
        response = await client.put(
            "/v2/orders",
            content=body,
            headers=self._signed_headers("PUT", "/v2/orders", body=body),
        )
        if response.status_code >= 400:
            detail = str(response.json().get("error", f"HTTP {response.status_code}"))
            raise ConflictError(f"Delta replace failed: {detail}")
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
            query = "?states=open,pending,closed,cancelled"
            try:
                response = await client.get(
                    f"/v2/orders{query}",
                    headers=self._signed_headers("GET", "/v2/orders", query=query),
                )
            except httpx.HTTPError as error:
                logger.warning("delta.poll_failed", error=type(error).__name__)
                await asyncio.sleep(_POLL_SECONDS * 2)
                continue
            if response.status_code == 200:
                for raw in response.json().get("result", []):
                    broker_order_id = str(raw.get("id", ""))
                    if broker_order_id not in self._tracked:
                        continue
                    status_raw = str(raw.get("state", "")).lower()
                    size = Decimal(str(raw.get("size", 0)))
                    unfilled = Decimal(str(raw.get("unfilled_size", 0) or 0))
                    filled = size - unfilled
                    fingerprint = (status_raw, str(filled))
                    if seen_state.get(broker_order_id) == fingerprint:
                        continue
                    seen_state[broker_order_id] = fingerprint
                    mapped = _DELTA_STATUS_MAP.get(status_raw)
                    if mapped is None:
                        continue
                    if mapped == "submitted" and filled > 0:
                        mapped = "partially_filled"
                    average = raw.get("average_fill_price")
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
        path = "/v2/wallet/balances"
        response = await client.get(path, headers=self._signed_headers("GET", path))
        if response.status_code != 200:
            return {}
        balances: dict[str, Decimal] = {}
        for entry in response.json().get("result", []):
            asset = str(entry.get("asset_symbol", ""))
            balances[asset] = Decimal(str(entry.get("available_balance", 0)))
        return balances

    async def get_positions(self) -> list[dict[str, object]]:
        client = self._require_client()
        path = "/v2/positions/margined"
        response = await client.get(path, headers=self._signed_headers("GET", path))
        if response.status_code != 200:
            return []
        return [dict(item) for item in response.json().get("result", [])]
