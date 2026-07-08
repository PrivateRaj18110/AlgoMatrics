"""Zerodha Kite Connect execution adapter (REST v3).

Implements ``BrokerExecutionPort`` against https://api.kite.trade. Order
updates are gathered by polling the orders endpoint; a WebSocket postback
upgrade can replace the poller without changing the port.
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
from algo_platform.modules.trading.domain.orders import OrderIntent, OrderStatus
from algo_platform.modules.trading.infrastructure.brokers.indian import (
    NSE_ORDER_STATUS_MAP,
    VenueInstrument,
    ensure_lot_multiple,
    to_nse_order_type,
    to_nse_transaction_type,
    to_nse_validity,
)
from algo_platform.shared.domain.errors import ConflictError
from algo_platform.shared.domain.types import utc_now

logger = structlog.get_logger(__name__)

_BASE = "https://api.kite.trade"
_TIMEOUT = httpx.Timeout(15.0)
_POLL_SECONDS = 2.0

SymbolResolver = Callable[[UUID], Awaitable[VenueInstrument]]


class ZerodhaExecutionAdapter:
    def __init__(
        self,
        *,
        api_key: str,
        access_token: str,
        symbol_resolver: SymbolResolver,
        product: str = "MIS",
    ) -> None:
        self._headers = {
            "X-Kite-Version": "3",
            "Authorization": f"token {api_key}:{access_token}",
        }
        self._resolve = symbol_resolver
        self._product = product
        self._client: httpx.AsyncClient | None = None
        self._tracked: dict[str, str] = {}  # broker_order_id -> client_order_id
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
            raise ConflictError("Zerodha adapter is not connected")
        return self._client

    async def health(self) -> bool:
        client = self._require_client()
        try:
            response = await client.get("/user/margins")
        except httpx.HTTPError:
            return False
        return response.status_code == 200

    async def submit_order(self, intent: OrderIntent) -> BrokerOrderAck:
        client = self._require_client()
        venue = await self._resolve(intent.instrument_id)
        quantity = ensure_lot_multiple(intent.quantity, venue.lot_size, venue.symbol)
        form: dict[str, str] = {
            "tradingsymbol": venue.symbol,
            "exchange": venue.exchange or "NSE",
            "transaction_type": to_nse_transaction_type(intent.side.value),
            "order_type": to_nse_order_type(intent.order_type),
            "quantity": str(quantity),
            "product": self._product,
            "validity": to_nse_validity(intent.time_in_force),
            "tag": intent.client_order_id[:20],
        }
        if intent.limit_price is not None:
            form["price"] = str(intent.limit_price)
        if intent.stop_price is not None:
            form["trigger_price"] = str(intent.stop_price)
        response = await client.post("/orders/regular", data=form)
        if response.status_code >= 400:
            detail = response.json().get("message", f"HTTP {response.status_code}")
            raise ConflictError(f"Kite rejected the order: {detail}")
        broker_order_id = str(response.json()["data"]["order_id"])
        self._tracked[broker_order_id] = intent.client_order_id
        return BrokerOrderAck(
            broker_order_id=broker_order_id,
            client_order_id=intent.client_order_id,
            status=OrderStatus.SUBMITTED,
            accepted_at=utc_now(),
        )

    async def cancel_order(self, broker_order_id: str) -> BrokerOrderAck:
        client = self._require_client()
        response = await client.delete(f"/orders/regular/{broker_order_id}")
        if response.status_code >= 400:
            detail = response.json().get("message", f"HTTP {response.status_code}")
            raise ConflictError(f"Kite cancel failed: {detail}")
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
        form: dict[str, str] = {}
        if quantity is not None:
            form["quantity"] = str(int(quantity))
        if limit_price is not None:
            form["price"] = str(limit_price)
        if stop_price is not None:
            form["trigger_price"] = str(stop_price)
        response = await client.put(f"/orders/regular/{broker_order_id}", data=form)
        if response.status_code >= 400:
            detail = response.json().get("message", f"HTTP {response.status_code}")
            raise ConflictError(f"Kite replace failed: {detail}")
        return BrokerOrderAck(
            broker_order_id=broker_order_id,
            client_order_id=self._tracked.get(broker_order_id, ""),
            status=OrderStatus.SUBMITTED,
            accepted_at=utc_now(),
        )

    async def stream_order_updates(self) -> AsyncIterator[BrokerOrderUpdate]:
        """Poll /orders and emit normalized updates for tracked orders."""
        seen_state: dict[str, tuple[str, str]] = {}
        while self._running:
            client = self._require_client()
            try:
                response = await client.get("/orders")
            except httpx.HTTPError as error:
                logger.warning("zerodha.poll_failed", error=type(error).__name__)
                await asyncio.sleep(_POLL_SECONDS * 2)
                continue
            if response.status_code == 200:
                for raw in response.json().get("data", []):
                    broker_order_id = str(raw.get("order_id", ""))
                    if broker_order_id not in self._tracked:
                        continue
                    status_raw = str(raw.get("status", "")).upper()
                    filled = Decimal(str(raw.get("filled_quantity", 0)))
                    fingerprint = (status_raw, str(filled))
                    if seen_state.get(broker_order_id) == fingerprint:
                        continue
                    seen_state[broker_order_id] = fingerprint
                    mapped = NSE_ORDER_STATUS_MAP.get(status_raw)
                    if mapped is None:
                        continue
                    average = raw.get("average_price")
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
        response = await client.get("/user/margins")
        if response.status_code != 200:
            return {}
        equity = response.json().get("data", {}).get("equity", {})
        available = equity.get("available", {})
        return {"cash": Decimal(str(available.get("cash", 0)))}

    async def get_positions(self) -> list[dict[str, object]]:
        client = self._require_client()
        response = await client.get("/portfolio/positions")
        if response.status_code != 200:
            return []
        raw = response.json().get("data", {}).get("net", [])
        return [dict(item) for item in raw]
