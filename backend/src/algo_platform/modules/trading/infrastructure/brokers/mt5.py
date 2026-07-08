"""MT5 execution adapter.

MT5 terminals run on a Windows VPS next to the broker; the platform never
talks to the terminal directly. This adapter is an HTTP client for the
Algo Matrics VPS agent (``agents/vps-agent``), which owns the MetaTrader5
API, translates retcodes/lots/symbols, and enforces its own idempotency.
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
from algo_platform.modules.trading.domain.orders import OrderIntent, OrderStatus
from algo_platform.modules.trading.infrastructure.brokers.indian import VenueInstrument
from algo_platform.shared.domain.errors import ConflictError
from algo_platform.shared.domain.types import utc_now

logger = structlog.get_logger(__name__)

_TIMEOUT = httpx.Timeout(20.0)
_POLL_SECONDS = 2.0

SymbolResolver = Callable[[UUID], Awaitable[VenueInstrument]]


class Mt5AgentExecutionAdapter:
    def __init__(
        self,
        *,
        agent_url: str,
        agent_token: str,
        symbol_resolver: SymbolResolver,
        allowed_hosts: frozenset[str] | None = None,
        require_https: bool = False,
    ) -> None:
        base = agent_url.rstrip("/")
        parsed = urlsplit(base)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username:
            raise ConflictError("MT5 agent URL is invalid")
        if require_https and parsed.scheme != "https":
            raise ConflictError("MT5 agent URL must use HTTPS")
        if allowed_hosts is not None and parsed.hostname.lower() not in allowed_hosts:
            raise ConflictError("MT5 agent host is not in the platform allowlist")
        self._base = base
        self._headers = {"Authorization": f"Bearer {agent_token}"}
        self._resolve = symbol_resolver
        self._client: httpx.AsyncClient | None = None
        self._tracked: dict[str, str] = {}
        self._running = False

    async def connect(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=self._base, headers=self._headers, timeout=_TIMEOUT
        )
        self._running = True

    async def disconnect(self) -> None:
        self._running = False
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise ConflictError("MT5 agent adapter is not connected")
        return self._client

    async def health(self) -> bool:
        client = self._require_client()
        try:
            response = await client.get("/health")
        except httpx.HTTPError:
            return False
        return response.status_code == 200 and bool(response.json().get("terminal_connected"))

    async def submit_order(self, intent: OrderIntent) -> BrokerOrderAck:
        client = self._require_client()
        venue = await self._resolve(intent.instrument_id)
        payload = {
            "client_order_id": intent.client_order_id,
            "symbol": venue.symbol,
            "side": intent.side.value,
            "order_type": intent.order_type.value,
            "volume": str(intent.quantity),
            "limit_price": str(intent.limit_price) if intent.limit_price else None,
            "stop_price": str(intent.stop_price) if intent.stop_price else None,
        }
        response = await client.post("/orders", json=payload)
        if response.status_code >= 400:
            detail = str(response.json().get("detail", f"HTTP {response.status_code}"))
            raise ConflictError(f"MT5 agent rejected the order: {detail}")
        broker_order_id = str(response.json()["order_id"])
        self._tracked[broker_order_id] = intent.client_order_id
        return BrokerOrderAck(
            broker_order_id=broker_order_id,
            client_order_id=intent.client_order_id,
            status=OrderStatus.SUBMITTED,
            accepted_at=utc_now(),
        )

    async def cancel_order(self, broker_order_id: str) -> BrokerOrderAck:
        client = self._require_client()
        response = await client.post(f"/orders/{broker_order_id}/cancel")
        if response.status_code >= 400:
            detail = str(response.json().get("detail", f"HTTP {response.status_code}"))
            raise ConflictError(f"MT5 agent cancel failed: {detail}")
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
        payload = {
            "volume": str(quantity) if quantity is not None else None,
            "limit_price": str(limit_price) if limit_price is not None else None,
            "stop_price": str(stop_price) if stop_price is not None else None,
        }
        response = await client.post(f"/orders/{broker_order_id}/replace", json=payload)
        if response.status_code >= 400:
            detail = str(response.json().get("detail", f"HTTP {response.status_code}"))
            raise ConflictError(f"MT5 agent replace failed: {detail}")
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
                response = await client.get("/orders")
            except httpx.HTTPError as error:
                logger.warning("mt5.poll_failed", error=type(error).__name__)
                await asyncio.sleep(_POLL_SECONDS * 2)
                continue
            if response.status_code == 200:
                for raw in response.json().get("orders", []):
                    broker_order_id = str(raw.get("order_id", ""))
                    if broker_order_id not in self._tracked:
                        continue
                    status_raw = str(raw.get("status", "")).lower()
                    filled = Decimal(str(raw.get("filled_volume", 0) or 0))
                    fingerprint = (status_raw, str(filled))
                    if seen_state.get(broker_order_id) == fingerprint:
                        continue
                    seen_state[broker_order_id] = fingerprint
                    try:
                        mapped = OrderStatus(status_raw)
                    except ValueError:
                        continue
                    average = raw.get("average_price")
                    yield BrokerOrderUpdate(
                        broker_order_id=broker_order_id,
                        client_order_id=self._tracked[broker_order_id],
                        status=mapped,
                        filled_quantity=filled,
                        average_price=Decimal(str(average)) if average else None,
                        occurred_at=utc_now(),
                        raw_reference=status_raw,
                    )
            await asyncio.sleep(_POLL_SECONDS)

    async def get_balances(self) -> dict[str, Decimal]:
        client = self._require_client()
        response = await client.get("/account")
        if response.status_code != 200:
            return {}
        data = response.json()
        return {
            str(data.get("currency", "USD")): Decimal(str(data.get("balance", 0))),
        }

    async def get_positions(self) -> list[dict[str, object]]:
        client = self._require_client()
        response = await client.get("/positions")
        if response.status_code != 200:
            return []
        return [dict(item) for item in response.json().get("positions", [])]
