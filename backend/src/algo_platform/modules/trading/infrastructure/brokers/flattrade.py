"""Flattrade execution adapter (Noren REST API).

Implements ``BrokerExecutionPort`` against https://piconnect.flattrade.in.
Flattrade exposes the NorenRest protocol: every call is a POST whose body is
``jData=<json>&jKey=<session token>``; responses carry ``stat: Ok | Not_Ok``.
Order updates are gathered by polling ``OrderBook``; the venue's WebSocket can
replace the poller later without changing the port.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
import structlog

from algo_platform.modules.trading.application.broker_port import (
    BrokerOrderAck,
    BrokerOrderUpdate,
)
from algo_platform.modules.trading.domain.orders import (
    OrderIntent,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from algo_platform.modules.trading.infrastructure.brokers.indian import (
    VenueInstrument,
    ensure_lot_multiple,
)
from algo_platform.shared.domain.errors import ConflictError, ValidationFailed
from algo_platform.shared.domain.types import utc_now

logger = structlog.get_logger(__name__)

_BASE = "https://piconnect.flattrade.in/PiConnectTP"
_TIMEOUT = httpx.Timeout(15.0)
_POLL_SECONDS = 2.0

SymbolResolver = Callable[[UUID], Awaitable[VenueInstrument]]

# Noren order-book statuses → platform statuses. Note the venue spells
# "CANCELED" with a single L.
_NOREN_STATUS_MAP = {
    "OPEN": "submitted",
    "PENDING": "submitted",
    "TRIGGER_PENDING": "submitted",
    "COMPLETE": "filled",
    "CANCELED": "cancelled",
    "REJECTED": "rejected",
}

_NOREN_ORDER_TYPE = {
    OrderType.MARKET: "MKT",
    OrderType.LIMIT: "LMT",
    OrderType.STOP: "SL-MKT",
    OrderType.STOP_LIMIT: "SL-LMT",
}


def _noren_validity(tif: TimeInForce) -> str:
    if tif is TimeInForce.DAY:
        return "DAY"
    if tif is TimeInForce.IOC:
        return "IOC"
    raise ValidationFailed(f"Flattrade does not support time-in-force '{tif.value}'")


@dataclass(slots=True)
class _TrackedOrder:
    client_order_id: str
    symbol: str
    exchange: str


class FlattradeExecutionAdapter:
    def __init__(
        self,
        *,
        client_code: str,
        session_token: str,
        symbol_resolver: SymbolResolver,
        product: str = "I",  # intraday (MIS); "C" would be CNC delivery
    ) -> None:
        self._uid = client_code
        self._token = session_token
        self._resolve = symbol_resolver
        self._product = product
        self._client: httpx.AsyncClient | None = None
        self._tracked: dict[str, _TrackedOrder] = {}
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
            raise ConflictError("Flattrade adapter is not connected")
        return self._client

    async def _post(self, path: str, jdata: dict[str, Any]) -> dict[str, Any] | list[Any]:
        """POST a Noren envelope; return the parsed JSON body."""
        client = self._require_client()
        body = f"jData={json.dumps(jdata, separators=(',', ':'))}&jKey={self._token}"
        response = await client.post(path, content=body, headers={"Content-Type": "text/plain"})
        if response.status_code >= 400:
            raise ConflictError(f"Flattrade returned HTTP {response.status_code}")
        parsed: dict[str, Any] | list[Any] = response.json()
        return parsed

    async def health(self) -> bool:
        try:
            body = await self._post("/Limits", {"uid": self._uid, "actid": self._uid})
        except (httpx.HTTPError, ConflictError):
            return False
        return isinstance(body, dict) and body.get("stat") == "Ok"

    async def submit_order(self, intent: OrderIntent) -> BrokerOrderAck:
        venue = await self._resolve(intent.instrument_id)
        quantity = ensure_lot_multiple(intent.quantity, venue.lot_size, venue.symbol)
        jdata: dict[str, Any] = {
            "uid": self._uid,
            "actid": self._uid,
            "exch": venue.exchange or "NSE",
            "tsym": venue.symbol,
            "qty": str(quantity),
            "prc": str(intent.limit_price) if intent.limit_price is not None else "0",
            "prd": self._product,
            "trantype": "B" if intent.side.value == "buy" else "S",
            "prctyp": _NOREN_ORDER_TYPE[intent.order_type],
            "ret": _noren_validity(intent.time_in_force),
            "remarks": intent.client_order_id[:50],
        }
        if intent.stop_price is not None:
            jdata["trgprc"] = str(intent.stop_price)
        body = await self._post("/PlaceOrder", jdata)
        if not isinstance(body, dict) or body.get("stat") != "Ok":
            detail = body.get("emsg", "order rejected") if isinstance(body, dict) else "bad reply"
            raise ConflictError(f"Flattrade rejected the order: {detail}")
        broker_order_id = str(body["norenordno"])
        self._tracked[broker_order_id] = _TrackedOrder(
            client_order_id=intent.client_order_id,
            symbol=venue.symbol,
            exchange=venue.exchange or "NSE",
        )
        return BrokerOrderAck(
            broker_order_id=broker_order_id,
            client_order_id=intent.client_order_id,
            status=OrderStatus.SUBMITTED,
            accepted_at=utc_now(),
        )

    async def cancel_order(self, broker_order_id: str) -> BrokerOrderAck:
        body = await self._post("/CancelOrder", {"uid": self._uid, "norenordno": broker_order_id})
        if not isinstance(body, dict) or body.get("stat") != "Ok":
            detail = body.get("emsg", "cancel failed") if isinstance(body, dict) else "bad reply"
            raise ConflictError(f"Flattrade cancel failed: {detail}")
        tracked = self._tracked.get(broker_order_id)
        return BrokerOrderAck(
            broker_order_id=broker_order_id,
            client_order_id=tracked.client_order_id if tracked else "",
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
        tracked = self._tracked.get(broker_order_id)
        if tracked is None:
            raise ConflictError("Flattrade replace requires an order tracked by this session")
        jdata: dict[str, Any] = {
            "uid": self._uid,
            "norenordno": broker_order_id,
            "exch": tracked.exchange,
            "tsym": tracked.symbol,
        }
        if quantity is not None:
            jdata["qty"] = str(int(quantity))
        if limit_price is not None:
            jdata["prc"] = str(limit_price)
            jdata["prctyp"] = "LMT"
        if stop_price is not None:
            jdata["trgprc"] = str(stop_price)
        body = await self._post("/ModifyOrder", jdata)
        if not isinstance(body, dict) or body.get("stat") != "Ok":
            detail = body.get("emsg", "replace failed") if isinstance(body, dict) else "bad reply"
            raise ConflictError(f"Flattrade replace failed: {detail}")
        return BrokerOrderAck(
            broker_order_id=broker_order_id,
            client_order_id=tracked.client_order_id,
            status=OrderStatus.SUBMITTED,
            accepted_at=utc_now(),
        )

    async def stream_order_updates(self) -> AsyncIterator[BrokerOrderUpdate]:
        """Poll OrderBook and emit normalized updates for tracked orders."""
        seen_state: dict[str, tuple[str, str]] = {}
        while self._running:
            try:
                body = await self._post("/OrderBook", {"uid": self._uid})
            except (httpx.HTTPError, ConflictError) as error:
                logger.warning("flattrade.poll_failed", error=type(error).__name__)
                await asyncio.sleep(_POLL_SECONDS * 2)
                continue
            rows = body if isinstance(body, list) else []
            for raw in rows:
                if not isinstance(raw, dict):
                    continue
                broker_order_id = str(raw.get("norenordno", ""))
                tracked = self._tracked.get(broker_order_id)
                if tracked is None:
                    continue
                status_raw = str(raw.get("status", "")).upper()
                filled = Decimal(str(raw.get("fillshares", 0) or 0))
                fingerprint = (status_raw, str(filled))
                if seen_state.get(broker_order_id) == fingerprint:
                    continue
                seen_state[broker_order_id] = fingerprint
                mapped = _NOREN_STATUS_MAP.get(status_raw)
                if mapped is None:
                    continue
                average = raw.get("avgprc")
                yield BrokerOrderUpdate(
                    broker_order_id=broker_order_id,
                    client_order_id=tracked.client_order_id,
                    status=OrderStatus(mapped),
                    filled_quantity=filled,
                    average_price=Decimal(str(average)) if average else None,
                    occurred_at=utc_now(),
                    raw_reference=str(raw.get("rejreason") or status_raw),
                )
            await asyncio.sleep(_POLL_SECONDS)

    async def get_balances(self) -> dict[str, Decimal]:
        body = await self._post("/Limits", {"uid": self._uid, "actid": self._uid})
        if not isinstance(body, dict) or body.get("stat") != "Ok":
            return {}
        return {"cash": Decimal(str(body.get("cash", 0) or 0))}

    async def get_positions(self) -> list[dict[str, object]]:
        body = await self._post("/PositionBook", {"uid": self._uid, "actid": self._uid})
        if not isinstance(body, list):
            return []
        return [dict(item) for item in body if isinstance(item, dict)]
