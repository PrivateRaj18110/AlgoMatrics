"""Interactive Brokers execution adapter (Client Portal Web API).

Talks to the IBKR Client Portal Gateway's REST API. Authentication is handled by
the gateway session (brokerage login + 2FA), so the credential here is the
gateway URL and the account id rather than a key/secret. Order placement uses
IBKR's reply-confirmation flow. https://interactivebrokers.github.io/cpwebapi/

The gateway URL is user-supplied, so it is restricted to HTTPS or a loopback
host to avoid server-side request forgery.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from decimal import Decimal
from urllib.parse import urlsplit
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

_TIMEOUT = httpx.Timeout(20.0)
_POLL_SECONDS = 2.0
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_MAX_REPLY_HOPS = 5

SymbolResolver = Callable[[UUID], Awaitable[VenueInstrument]]

_IBKR_STATUS_MAP = {
    "presubmitted": "submitted",
    "submitted": "submitted",
    "pendingsubmit": "submitted",
    "filled": "filled",
    "cancelled": "cancelled",
    "pendingcancel": "cancel_pending",
    "inactive": "rejected",
    "rejected": "rejected",
}


def _validate_gateway_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValidationFailed("IBKR gateway URL must be an http(s) URL")
    if parts.scheme == "http" and parts.hostname not in _LOOPBACK_HOSTS:
        raise ValidationFailed("IBKR gateway URL must use HTTPS unless it is loopback")
    return url.rstrip("/")


class IbkrExecutionAdapter:
    def __init__(
        self, *, gateway_url: str, account_id: str, symbol_resolver: SymbolResolver
    ) -> None:
        self._gateway_url = gateway_url
        self._account_id = account_id
        self._resolve = symbol_resolver
        self._client: httpx.AsyncClient | None = None
        self._tracked: dict[str, str] = {}
        self._running = False

    async def connect(self) -> None:
        base = _validate_gateway_url(self._gateway_url)
        # The IBKR gateway ships a self-signed cert on loopback; verify real hosts.
        host = urlsplit(base).hostname
        verify = host not in _LOOPBACK_HOSTS
        self._client = httpx.AsyncClient(base_url=base, timeout=_TIMEOUT, verify=verify)
        self._running = True

    async def disconnect(self) -> None:
        self._running = False
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise ConflictError("IBKR adapter is not connected")
        return self._client

    async def health(self) -> bool:
        client = self._require_client()
        try:
            response = await client.post("/v1/api/iserver/auth/status")
        except httpx.HTTPError:
            return False
        return response.status_code == 200 and bool(response.json().get("authenticated"))

    async def submit_order(self, intent: OrderIntent) -> BrokerOrderAck:
        client = self._require_client()
        venue = await self._resolve(intent.instrument_id)
        if not venue.token:
            raise ValidationFailed("IBKR requires a numeric conid mapping for the instrument")
        order: dict[str, object] = {
            "conid": int(venue.token),
            "orderType": _ibkr_type(intent.order_type),
            "side": intent.side.value.upper(),
            "quantity": float(intent.quantity),
            "tif": "IOC" if intent.time_in_force.value == "ioc" else "DAY",
            "cOID": intent.client_order_id,
        }
        if intent.order_type in {OrderType.LIMIT, OrderType.STOP_LIMIT}:
            order["price"] = float(intent.limit_price or 0)
        if intent.order_type in {OrderType.STOP, OrderType.STOP_LIMIT}:
            order["auxPrice"] = float(intent.stop_price or 0)
        response = await client.post(
            f"/v1/api/iserver/account/{self._account_id}/orders", json={"orders": [order]}
        )
        broker_order_id = await self._resolve_reply(client, response)
        self._tracked[broker_order_id] = intent.client_order_id
        return BrokerOrderAck(
            broker_order_id=broker_order_id,
            client_order_id=intent.client_order_id,
            status=OrderStatus.SUBMITTED,
            accepted_at=utc_now(),
        )

    async def _resolve_reply(self, client: httpx.AsyncClient, response: httpx.Response) -> str:
        """Walk IBKR's confirmation prompts until an order id is returned."""
        for _ in range(_MAX_REPLY_HOPS):
            if response.status_code >= 400:
                raise ConflictError(f"IBKR rejected the order: HTTP {response.status_code}")
            entries = response.json()
            if not isinstance(entries, list) or not entries:
                raise ConflictError("IBKR returned no order acknowledgement")
            first = entries[0]
            if first.get("order_id"):
                return str(first["order_id"])
            reply_id = first.get("id")
            if not reply_id:
                raise ConflictError("IBKR order was not accepted")
            response = await client.post(
                f"/v1/api/iserver/reply/{reply_id}", json={"confirmed": True}
            )
        raise ConflictError("IBKR order confirmation did not complete")

    async def cancel_order(self, broker_order_id: str) -> BrokerOrderAck:
        client = self._require_client()
        response = await client.delete(
            f"/v1/api/iserver/account/{self._account_id}/order/{broker_order_id}"
        )
        if response.status_code >= 400:
            raise ConflictError(f"IBKR cancel failed: HTTP {response.status_code}")
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
        body: dict[str, object] = {}
        if quantity is not None:
            body["quantity"] = float(quantity)
        if limit_price is not None:
            body["price"] = float(limit_price)
        if stop_price is not None:
            body["auxPrice"] = float(stop_price)
        response = await client.post(
            f"/v1/api/iserver/account/{self._account_id}/order/{broker_order_id}", json=body
        )
        new_id = await self._resolve_reply(client, response)
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
            try:
                response = await client.get("/v1/api/iserver/account/orders")
            except httpx.HTTPError as error:
                logger.warning("ibkr.poll_failed", error=type(error).__name__)
                await asyncio.sleep(_POLL_SECONDS * 2)
                continue
            if response.status_code == 200:
                for raw in response.json().get("orders", []):
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
        status_raw = str(raw.get("status", "")).lower()
        filled = Decimal(str(raw.get("filledQuantity", 0) or 0))
        fingerprint = (status_raw, str(filled))
        if seen_state.get(broker_order_id) == fingerprint:
            return None
        seen_state[broker_order_id] = fingerprint
        mapped = _IBKR_STATUS_MAP.get(status_raw)
        if mapped is None:
            return None
        if mapped == "submitted" and filled > 0:
            mapped = "partially_filled"
        average = raw.get("avgPrice")
        return BrokerOrderUpdate(
            broker_order_id=broker_order_id,
            client_order_id=self._tracked[broker_order_id],
            status=OrderStatus(mapped),
            filled_quantity=filled,
            average_price=Decimal(str(average)) if average else None,
            occurred_at=utc_now(),
            raw_reference=status_raw,
        )

    async def get_balances(self) -> dict[str, Decimal]:
        client = self._require_client()
        response = await client.get(f"/v1/api/portfolio/{self._account_id}/ledger")
        if response.status_code != 200:
            return {}
        balances: dict[str, Decimal] = {}
        for currency, entry in response.json().items():
            if isinstance(entry, dict) and "cashbalance" in entry:
                balances[str(currency)] = Decimal(str(entry.get("cashbalance", 0)))
        return balances

    async def get_positions(self) -> list[dict[str, object]]:
        client = self._require_client()
        response = await client.get(f"/v1/api/portfolio/{self._account_id}/positions/0")
        if response.status_code != 200:
            return []
        return [dict(item) for item in response.json()]


def _ibkr_type(order_type: OrderType) -> str:
    return {
        OrderType.MARKET: "MKT",
        OrderType.LIMIT: "LMT",
        OrderType.STOP: "STP",
        OrderType.STOP_LIMIT: "STOP_LIMIT",
    }.get(order_type, "LMT")
