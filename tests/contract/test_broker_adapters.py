"""Contract tests for the live broker execution adapters.

Each adapter's real request-building and response-parsing logic runs against
recorded-shape fixtures served through ``httpx.MockTransport``. Only the network
transport is substituted; the adapter's protocol behaviour (endpoints, payload
shapes, retcode/status normalization) is exercised end to end.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from urllib.parse import parse_qs
from uuid import UUID, uuid4

import httpx
import pytest

from algo_platform.modules.trading.application.broker_port import BrokerOrderUpdate
from algo_platform.modules.trading.domain.orders import (
    OrderIntent,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from algo_platform.modules.trading.infrastructure.brokers.angelone import (
    AngelOneExecutionAdapter,
)
from algo_platform.modules.trading.infrastructure.brokers.binance import (
    BinanceExecutionAdapter,
)
from algo_platform.modules.trading.infrastructure.brokers.delta import DeltaExecutionAdapter
from algo_platform.modules.trading.infrastructure.brokers.ibkr import (
    IbkrExecutionAdapter,
    _validate_gateway_url,
)
from algo_platform.modules.trading.infrastructure.brokers.indian import VenueInstrument
from algo_platform.modules.trading.infrastructure.brokers.mt5 import Mt5AgentExecutionAdapter
from algo_platform.modules.trading.infrastructure.brokers.paper import (
    PaperExecutionSimulator,
    PaperMarketState,
)
from algo_platform.modules.trading.infrastructure.brokers.registry import (
    BrokerAdapterRegistry,
)
from algo_platform.modules.trading.infrastructure.brokers.zerodha import (
    ZerodhaExecutionAdapter,
)
from algo_platform.shared.domain.errors import ConflictError, ValidationFailed
from algo_platform.shared.domain.types import AccountId, Side, StrategyRunId, TenantId

pytestmark = pytest.mark.contract

Route = tuple[str, str]
Handler = Callable[[httpx.Request], httpx.Response]


def _intent(**overrides: object) -> OrderIntent:
    base: dict[str, object] = {
        "tenant_id": TenantId(uuid4()),
        "account_id": AccountId(uuid4()),
        "strategy_run_id": StrategyRunId(uuid4()),
        "instrument_id": uuid4(),
        "side": Side.BUY,
        "quantity": Decimal("10"),
        "order_type": OrderType.MARKET,
        "time_in_force": TimeInForce.DAY,
        "client_order_id": "cid-1",
    }
    base.update(overrides)
    return OrderIntent(**base)  # type: ignore[arg-type]


async def _venue(_instrument_id: UUID) -> VenueInstrument:
    return VenueInstrument(symbol="RELIANCE", exchange="NSE", lot_size=Decimal("1"), token="2885")


def _router(
    routes: dict[Route, tuple[int, dict[str, object]]], captured: list[httpx.Request]
) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        payload = routes.get((request.method, request.url.path))
        if payload is None:
            return httpx.Response(404, json={"message": "no route", "error": "no route"})
        status, body = payload
        return httpx.Response(status, json=body)

    return handler


def _attach(adapter: object, handler: Handler, base_url: str) -> None:
    adapter._client = httpx.AsyncClient(  # type: ignore[attr-defined]
        base_url=base_url, transport=httpx.MockTransport(handler)
    )
    adapter._running = True  # type: ignore[attr-defined]


async def _first_update(adapter: object) -> BrokerOrderUpdate:
    agen = adapter.stream_order_updates()  # type: ignore[attr-defined]
    try:
        return await agen.__anext__()
    finally:
        adapter._running = False  # type: ignore[attr-defined]
        await agen.aclose()


# --------------------------------- Zerodha ----------------------------------


class TestZerodhaAdapter:
    def _adapter(self) -> ZerodhaExecutionAdapter:
        return ZerodhaExecutionAdapter(api_key="key", access_token="token", symbol_resolver=_venue)

    async def test_connect_and_disconnect(self) -> None:
        adapter = self._adapter()
        await adapter.connect()
        assert adapter._client is not None
        await adapter.disconnect()
        assert adapter._client is None

    async def test_submit_market_order_builds_kite_form(self) -> None:
        adapter = self._adapter()
        captured: list[httpx.Request] = []
        _attach(
            adapter,
            _router(
                {("POST", "/orders/regular"): (200, {"data": {"order_id": "24010100001"}})},
                captured,
            ),
            "https://api.kite.trade",
        )
        ack = await adapter.submit_order(_intent())
        assert ack.broker_order_id == "24010100001"
        assert ack.status is OrderStatus.SUBMITTED
        form = parse_qs(captured[0].content.decode())
        assert form["tradingsymbol"] == ["RELIANCE"]
        assert form["transaction_type"] == ["BUY"]
        assert form["order_type"] == ["MARKET"]
        assert form["quantity"] == ["10"]
        assert form["validity"] == ["DAY"]

    async def test_submit_limit_order_includes_price(self) -> None:
        adapter = self._adapter()
        captured: list[httpx.Request] = []
        _attach(
            adapter,
            _router({("POST", "/orders/regular"): (200, {"data": {"order_id": "1"}})}, captured),
            "https://api.kite.trade",
        )
        await adapter.submit_order(
            _intent(order_type=OrderType.LIMIT, limit_price=Decimal("2950.5"))
        )
        form = parse_qs(captured[0].content.decode())
        assert form["price"] == ["2950.5"]
        assert form["order_type"] == ["LIMIT"]

    async def test_rejected_order_raises_conflict(self) -> None:
        adapter = self._adapter()
        _attach(
            adapter,
            _router({("POST", "/orders/regular"): (400, {"message": "insufficient funds"})}, []),
            "https://api.kite.trade",
        )
        with pytest.raises(ConflictError, match="insufficient funds"):
            await adapter.submit_order(_intent())

    async def test_cancel_and_replace(self) -> None:
        adapter = self._adapter()
        captured: list[httpx.Request] = []
        _attach(
            adapter,
            _router(
                {
                    ("DELETE", "/orders/regular/o1"): (200, {"data": {"order_id": "o1"}}),
                    ("PUT", "/orders/regular/o1"): (200, {"data": {"order_id": "o1"}}),
                },
                captured,
            ),
            "https://api.kite.trade",
        )
        cancel = await adapter.cancel_order("o1")
        assert cancel.status is OrderStatus.CANCEL_PENDING
        replace = await adapter.replace_order(
            "o1", quantity=Decimal("5"), limit_price=Decimal("10")
        )
        assert replace.status is OrderStatus.SUBMITTED

    async def test_stream_normalizes_complete_status(self) -> None:
        adapter = self._adapter()
        adapter._tracked["o9"] = "cid-9"
        _attach(
            adapter,
            _router(
                {
                    ("GET", "/orders"): (
                        200,
                        {
                            "data": [
                                {
                                    "order_id": "o9",
                                    "status": "COMPLETE",
                                    "filled_quantity": 10,
                                    "average_price": 2951.25,
                                }
                            ]
                        },
                    )
                },
                [],
            ),
            "https://api.kite.trade",
        )
        update = await _first_update(adapter)
        assert update.status is OrderStatus.FILLED
        assert update.filled_quantity == Decimal("10")
        assert update.average_price == Decimal("2951.25")

    async def test_balances_and_positions(self) -> None:
        adapter = self._adapter()
        _attach(
            adapter,
            _router(
                {
                    ("GET", "/user/margins"): (
                        200,
                        {"data": {"equity": {"available": {"cash": 15000}}}},
                    ),
                    ("GET", "/portfolio/positions"): (
                        200,
                        {"data": {"net": [{"tradingsymbol": "X"}]}},
                    ),
                },
                [],
            ),
            "https://api.kite.trade",
        )
        assert await adapter.health() is True
        balances = await adapter.get_balances()
        assert balances["cash"] == Decimal("15000")
        positions = await adapter.get_positions()
        assert positions == [{"tradingsymbol": "X"}]


# --------------------------------- Angel One --------------------------------


class TestAngelOneAdapter:
    def _adapter(self) -> AngelOneExecutionAdapter:
        return AngelOneExecutionAdapter(
            api_key="key",
            jwt_token="jwt",
            client_code="C1",
            symbol_resolver=_venue,
        )

    async def test_submit_uses_symbol_token(self) -> None:
        adapter = self._adapter()
        captured: list[httpx.Request] = []
        _attach(
            adapter,
            _router(
                {
                    ("POST", "/rest/secure/angelbroking/order/v1/placeOrder"): (
                        200,
                        {"status": True, "data": {"orderid": "AO-1"}},
                    )
                },
                captured,
            ),
            "https://apiconnect.angelone.in",
        )
        ack = await adapter.submit_order(_intent())
        assert ack.broker_order_id == "AO-1"
        import json

        body = json.loads(captured[0].content.decode())
        assert body["symboltoken"] == "2885"
        assert body["transactiontype"] == "BUY"
        assert body["ordertype"] == "MARKET"

    async def test_status_false_is_rejection(self) -> None:
        adapter = self._adapter()
        _attach(
            adapter,
            _router(
                {
                    ("POST", "/rest/secure/angelbroking/order/v1/placeOrder"): (
                        200,
                        {"status": False, "message": "RMS blocked"},
                    )
                },
                [],
            ),
            "https://apiconnect.angelone.in",
        )
        with pytest.raises(ConflictError, match="RMS blocked"):
            await adapter.submit_order(_intent())

    async def test_stream_maps_complete(self) -> None:
        adapter = self._adapter()
        adapter._tracked["AO-9"] = "cid-9"
        _attach(
            adapter,
            _router(
                {
                    ("GET", "/rest/secure/angelbroking/order/v1/getOrderBook"): (
                        200,
                        {
                            "status": True,
                            "data": [
                                {
                                    "orderid": "AO-9",
                                    "status": "complete",
                                    "filledshares": 10,
                                    "averageprice": 100.5,
                                }
                            ],
                        },
                    )
                },
                [],
            ),
            "https://apiconnect.angelone.in",
        )
        update = await _first_update(adapter)
        assert update.status is OrderStatus.FILLED
        assert update.average_price == Decimal("100.5")

    async def test_balances(self) -> None:
        adapter = self._adapter()
        _attach(
            adapter,
            _router(
                {
                    ("GET", "/rest/secure/angelbroking/user/v1/getRMS"): (
                        200,
                        {"status": True, "data": {"availablecash": "5000"}},
                    )
                },
                [],
            ),
            "https://apiconnect.angelone.in",
        )
        balances = await adapter.get_balances()
        assert balances["cash"] == Decimal("5000")


# ---------------------------------- Delta -----------------------------------


class TestDeltaAdapter:
    def _adapter(self) -> DeltaExecutionAdapter:
        return DeltaExecutionAdapter(api_key="key", api_secret="secret", symbol_resolver=_venue)

    async def test_submit_resolves_product_and_signs(self) -> None:
        adapter = self._adapter()
        captured: list[httpx.Request] = []
        _attach(
            adapter,
            _router(
                {
                    ("GET", "/v2/products/RELIANCE"): (200, {"result": {"id": 27}}),
                    ("POST", "/v2/orders"): (200, {"result": {"id": 5551}}),
                },
                captured,
            ),
            "https://api.india.delta.exchange",
        )
        ack = await adapter.submit_order(_intent())
        assert ack.broker_order_id == "5551"
        order_request = next(r for r in captured if r.url.path == "/v2/orders")
        assert order_request.headers["api-key"] == "key"
        assert "signature" in order_request.headers
        import json

        body = json.loads(order_request.content.decode())
        assert body["product_id"] == 27
        assert body["side"] == "buy"

    async def test_product_lookup_failure_raises(self) -> None:
        adapter = self._adapter()
        _attach(
            adapter,
            _router({("GET", "/v2/products/RELIANCE"): (404, {"error": "missing"})}, []),
            "https://api.india.delta.exchange",
        )
        with pytest.raises(Exception, match="not found"):
            await adapter.submit_order(_intent())

    async def test_stream_partial_fill(self) -> None:
        adapter = self._adapter()
        adapter._tracked["5551"] = "cid-1"
        _attach(
            adapter,
            _router(
                {
                    ("GET", "/v2/orders"): (
                        200,
                        {
                            "result": [
                                {
                                    "id": 5551,
                                    "state": "open",
                                    "size": 10,
                                    "unfilled_size": 4,
                                    "average_fill_price": "101.0",
                                }
                            ]
                        },
                    )
                },
                [],
            ),
            "https://api.india.delta.exchange",
        )
        update = await _first_update(adapter)
        assert update.status is OrderStatus.PARTIALLY_FILLED
        assert update.filled_quantity == Decimal("6")

    async def test_balances_indexed_by_asset(self) -> None:
        adapter = self._adapter()
        _attach(
            adapter,
            _router(
                {
                    ("GET", "/v2/wallet/balances"): (
                        200,
                        {"result": [{"asset_symbol": "USDT", "available_balance": "1200.5"}]},
                    )
                },
                [],
            ),
            "https://api.india.delta.exchange",
        )
        balances = await adapter.get_balances()
        assert balances["USDT"] == Decimal("1200.5")


# ----------------------------------- MT5 ------------------------------------


class TestMt5Adapter:
    def _adapter(self, **overrides: object) -> Mt5AgentExecutionAdapter:
        params: dict[str, object] = {
            "agent_url": "https://vps.example.com",
            "agent_token": "agent-token",
            "symbol_resolver": _venue,
            "allowed_hosts": frozenset({"vps.example.com"}),
            "require_https": True,
        }
        params.update(overrides)
        return Mt5AgentExecutionAdapter(**params)  # type: ignore[arg-type]

    def test_rejects_non_http_scheme(self) -> None:
        with pytest.raises(ConflictError, match="invalid"):
            self._adapter(
                agent_url="ftp://vps.example.com", allowed_hosts=None, require_https=False
            )

    def test_requires_https_outside_local(self) -> None:
        with pytest.raises(ConflictError, match="HTTPS"):
            self._adapter(agent_url="http://vps.example.com")

    def test_enforces_host_allowlist(self) -> None:
        with pytest.raises(ConflictError, match="allowlist"):
            self._adapter(agent_url="https://evil.example.com")

    async def test_submit_forwards_to_agent(self) -> None:
        adapter = self._adapter()
        captured: list[httpx.Request] = []
        _attach(
            adapter,
            _router({("POST", "/orders"): (200, {"order_id": "MT5-1"})}, captured),
            "https://vps.example.com",
        )
        ack = await adapter.submit_order(_intent())
        assert ack.broker_order_id == "MT5-1"
        import json

        body = json.loads(captured[0].content.decode())
        assert body["symbol"] == "RELIANCE"
        assert body["order_type"] == "market"

    async def test_health_requires_terminal_connected(self) -> None:
        adapter = self._adapter()
        _attach(
            adapter,
            _router({("GET", "/health"): (200, {"terminal_connected": True})}, []),
            "https://vps.example.com",
        )
        assert await adapter.health() is True

    async def test_stream_maps_native_status(self) -> None:
        adapter = self._adapter()
        adapter._tracked["MT5-9"] = "cid-9"
        _attach(
            adapter,
            _router(
                {
                    ("GET", "/orders"): (
                        200,
                        {
                            "orders": [
                                {
                                    "order_id": "MT5-9",
                                    "status": "filled",
                                    "filled_volume": 10,
                                    "average_price": 1.2345,
                                }
                            ]
                        },
                    )
                },
                [],
            ),
            "https://vps.example.com",
        )
        update = await _first_update(adapter)
        assert update.status is OrderStatus.FILLED
        assert update.filled_quantity == Decimal("10")

    async def test_cancel_failure_raises(self) -> None:
        adapter = self._adapter()
        _attach(
            adapter,
            _router({("POST", "/orders/MT5-1/cancel"): (409, {"detail": "already filled"})}, []),
            "https://vps.example.com",
        )
        with pytest.raises(ConflictError, match="already filled"):
            await adapter.cancel_order("MT5-1")


# --------------------------------- Registry ---------------------------------


class TestBrokerRegistry:
    def test_register_and_create(self) -> None:
        registry = BrokerAdapterRegistry()
        sentinel = object()
        registry.register("paper", lambda: sentinel)  # type: ignore[arg-type,return-value]
        assert registry.create("paper") is sentinel

    def test_duplicate_registration_rejected(self) -> None:
        registry = BrokerAdapterRegistry()
        registry.register("paper", lambda: object())  # type: ignore[arg-type,return-value]
        with pytest.raises(ValueError, match="already registered"):
            registry.register("paper", lambda: object())  # type: ignore[arg-type,return-value]

    def test_unknown_broker_rejected(self) -> None:
        registry = BrokerAdapterRegistry()
        with pytest.raises(ValueError, match="unsupported broker"):
            registry.create("nope")


def _raise(_request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("boom")


# --------------------- additional adapter path coverage ---------------------


class TestAdapterFailurePaths:
    async def test_zerodha_health_false_on_transport_error(self) -> None:
        adapter = ZerodhaExecutionAdapter(api_key="k", access_token="t", symbol_resolver=_venue)
        _attach(adapter, _raise, "https://api.kite.trade")
        assert await adapter.health() is False

    async def test_angelone_cancel_and_replace(self) -> None:
        adapter = AngelOneExecutionAdapter(
            api_key="k", jwt_token="j", client_code="C1", symbol_resolver=_venue
        )
        _attach(
            adapter,
            _router(
                {
                    ("POST", "/rest/secure/angelbroking/order/v1/cancelOrder"): (
                        200,
                        {"status": True},
                    ),
                    ("POST", "/rest/secure/angelbroking/order/v1/modifyOrder"): (
                        200,
                        {"status": True},
                    ),
                },
                [],
            ),
            "https://apiconnect.angelone.in",
        )
        cancel = await adapter.cancel_order("AO-1")
        assert cancel.status is OrderStatus.CANCEL_PENDING
        replace = await adapter.replace_order("AO-1", quantity=Decimal("5"))
        assert replace.status is OrderStatus.SUBMITTED

    async def test_angelone_positions(self) -> None:
        adapter = AngelOneExecutionAdapter(
            api_key="k", jwt_token="j", client_code="C1", symbol_resolver=_venue
        )
        _attach(
            adapter,
            _router(
                {
                    ("GET", "/rest/secure/angelbroking/order/v1/getPosition"): (
                        200,
                        {"status": True, "data": [{"tradingsymbol": "X"}]},
                    )
                },
                [],
            ),
            "https://apiconnect.angelone.in",
        )
        assert await adapter.get_positions() == [{"tradingsymbol": "X"}]

    async def test_delta_cancel_and_replace(self) -> None:
        adapter = DeltaExecutionAdapter(api_key="k", api_secret="s", symbol_resolver=_venue)
        _attach(
            adapter,
            _router(
                {
                    ("DELETE", "/v2/orders/5551"): (200, {"result": {}}),
                    ("PUT", "/v2/orders"): (200, {"result": {}}),
                },
                [],
            ),
            "https://api.india.delta.exchange",
        )
        cancel = await adapter.cancel_order("5551")
        assert cancel.status is OrderStatus.CANCEL_PENDING
        replace = await adapter.replace_order("5551", limit_price=Decimal("10"))
        assert replace.status is OrderStatus.SUBMITTED

    async def test_delta_positions(self) -> None:
        adapter = DeltaExecutionAdapter(api_key="k", api_secret="s", symbol_resolver=_venue)
        _attach(
            adapter,
            _router({("GET", "/v2/positions/margined"): (200, {"result": [{"size": 1}]})}, []),
            "https://api.india.delta.exchange",
        )
        assert await adapter.get_positions() == [{"size": 1}]

    async def test_mt5_replace_and_balances_and_positions(self) -> None:
        adapter = Mt5AgentExecutionAdapter(
            agent_url="https://vps.example.com",
            agent_token="t",
            symbol_resolver=_venue,
            allowed_hosts=frozenset({"vps.example.com"}),
            require_https=True,
        )
        _attach(
            adapter,
            _router(
                {
                    ("POST", "/orders/MT5-1/replace"): (200, {}),
                    ("GET", "/account"): (200, {"currency": "USD", "balance": "2500"}),
                    ("GET", "/positions"): (200, {"positions": [{"symbol": "EURUSD"}]}),
                },
                [],
            ),
            "https://vps.example.com",
        )
        replace = await adapter.replace_order("MT5-1", quantity=Decimal("2"))
        assert replace.status is OrderStatus.SUBMITTED
        assert (await adapter.get_balances())["USD"] == Decimal("2500")
        assert await adapter.get_positions() == [{"symbol": "EURUSD"}]

    async def test_mt5_health_false_when_terminal_down(self) -> None:
        adapter = Mt5AgentExecutionAdapter(
            agent_url="http://localhost:9000",
            agent_token="t",
            symbol_resolver=_venue,
        )
        _attach(
            adapter,
            _router({("GET", "/health"): (200, {"terminal_connected": False})}, []),
            "http://localhost:9000",
        )
        assert await adapter.health() is False


# ------------------------------- Paper venue --------------------------------


class TestPaperBrokerContract:
    """The built-in simulated venue's fill contract must be deterministic."""

    def _market(self) -> PaperMarketState:
        return PaperMarketState(bid=Decimal("100"), ask=Decimal("100.10"))

    def test_same_order_id_and_market_reproduce_fill(self) -> None:
        sim_a = PaperExecutionSimulator(seed=7)
        sim_b = PaperExecutionSimulator(seed=7)
        order_id = uuid4()
        fill_a = sim_a.fill_market_order(
            order_id=order_id,
            side=Side.BUY,
            remaining_quantity=Decimal("10"),
            market=self._market(),
        )
        fill_b = sim_b.fill_market_order(
            order_id=order_id,
            side=Side.BUY,
            remaining_quantity=Decimal("10"),
            market=self._market(),
        )
        assert (fill_a.quantity, fill_a.price, fill_a.fee) == (
            fill_b.quantity,
            fill_b.price,
            fill_b.fee,
        )

    def test_buy_market_fills_at_or_above_ask(self) -> None:
        sim = PaperExecutionSimulator(seed=1, partial_fill_probability=0.0)
        market = self._market()
        fill = sim.fill_market_order(
            order_id=uuid4(), side=Side.BUY, remaining_quantity=Decimal("5"), market=market
        )
        assert fill.price >= market.ask
        assert fill.quantity == Decimal("5")
        assert fill.fee > 0

    def test_limit_order_only_fills_when_crossed(self) -> None:
        sim = PaperExecutionSimulator(seed=1)
        market = self._market()
        order_id = uuid4()
        not_crossed = sim.try_fill_limit_order(
            order_id=order_id,
            side=Side.BUY,
            remaining_quantity=Decimal("5"),
            limit_price=Decimal("99"),
            market=market,
        )
        assert not_crossed is None
        crossed = sim.try_fill_limit_order(
            order_id=order_id,
            side=Side.BUY,
            remaining_quantity=Decimal("5"),
            limit_price=Decimal("101"),
            market=market,
        )
        assert crossed is not None
        assert crossed.price == Decimal("101")

    def test_stop_trigger_semantics(self) -> None:
        sim = PaperExecutionSimulator()
        market = self._market()
        assert sim.stop_triggered(side=Side.BUY, stop_price=Decimal("100.05"), market=market)
        assert not sim.stop_triggered(side=Side.BUY, stop_price=Decimal("101"), market=market)
        assert sim.stop_triggered(side=Side.SELL, stop_price=Decimal("100.5"), market=market)


# --------------------------------- Binance ----------------------------------


class TestBinanceAdapter:
    def _adapter(self) -> BinanceExecutionAdapter:
        return BinanceExecutionAdapter(api_key="key", api_secret="secret", symbol_resolver=_venue)

    async def test_submit_market_order_signs_and_tracks(self) -> None:
        captured: list[httpx.Request] = []
        handler = _router({("POST", "/api/v3/order"): (200, {"orderId": 555})}, captured)
        adapter = self._adapter()
        _attach(adapter, handler, "https://api.binance.com")

        ack = await adapter.submit_order(_intent())
        assert ack.broker_order_id == "555"
        assert ack.status is OrderStatus.SUBMITTED
        query = parse_qs(captured[0].url.query.decode())
        assert query["side"] == ["BUY"]
        assert query["type"] == ["MARKET"]
        assert query["quantity"] == ["10"]
        assert "signature" in query  # request was HMAC-signed

    async def test_submit_limit_includes_price_and_tif(self) -> None:
        captured: list[httpx.Request] = []
        handler = _router({("POST", "/api/v3/order"): (200, {"orderId": 1})}, captured)
        adapter = self._adapter()
        _attach(adapter, handler, "https://api.binance.com")

        await adapter.submit_order(
            _intent(order_type=OrderType.LIMIT, limit_price=Decimal("100.5"),
                    time_in_force=TimeInForce.IOC)
        )
        query = parse_qs(captured[0].url.query.decode())
        assert query["price"] == ["100.5"]
        assert query["timeInForce"] == ["IOC"]

    async def test_rejected_order_raises_conflict(self) -> None:
        handler = _router({("POST", "/api/v3/order"): (400, {"msg": "insufficient balance"})}, [])
        adapter = self._adapter()
        _attach(adapter, handler, "https://api.binance.com")
        with pytest.raises(ConflictError):
            await adapter.submit_order(_intent())

    async def test_stream_normalizes_filled(self) -> None:
        captured: list[httpx.Request] = []
        handler = _router(
            {
                ("POST", "/api/v3/order"): (200, {"orderId": 9}),
                ("GET", "/api/v3/openOrders"): (
                    200,
                    [{"orderId": 9, "status": "FILLED", "executedQty": "10",
                      "cummulativeQuoteQty": "1000"}],
                ),
            },
            captured,
        )
        adapter = self._adapter()
        _attach(adapter, handler, "https://api.binance.com")
        await adapter.submit_order(_intent())
        update = await _first_update(adapter)
        assert update.status is OrderStatus.FILLED
        assert update.filled_quantity == Decimal("10")
        assert update.average_price == Decimal("100")

    async def test_balances_filters_zero(self) -> None:
        handler = _router(
            {("GET", "/api/v3/account"): (
                200,
                {"balances": [{"asset": "USDT", "free": "500"}, {"asset": "BTC", "free": "0"}]},
            )},
            [],
        )
        adapter = self._adapter()
        _attach(adapter, handler, "https://api.binance.com")
        balances = await adapter.get_balances()
        assert balances == {"USDT": Decimal("500")}


# ----------------------------- Interactive Brokers --------------------------


class TestIbkrAdapter:
    def _adapter(self) -> IbkrExecutionAdapter:
        return IbkrExecutionAdapter(
            gateway_url="https://localhost:5000", account_id="DU123", symbol_resolver=_venue
        )

    def test_gateway_url_validation(self) -> None:
        assert _validate_gateway_url("https://gw.example.com/") == "https://gw.example.com"
        assert _validate_gateway_url("http://localhost:5000") == "http://localhost:5000"
        with pytest.raises(ValidationFailed):
            _validate_gateway_url("http://evil.example.com")
        with pytest.raises(ValidationFailed):
            _validate_gateway_url("ftp://localhost")

    async def test_submit_walks_reply_confirmation(self) -> None:
        captured: list[httpx.Request] = []
        handler = _router(
            {
                ("POST", "/v1/api/iserver/account/DU123/orders"): (
                    200,
                    [{"id": "reply1", "message": ["Confirm order?"]}],
                ),
                ("POST", "/v1/api/iserver/reply/reply1"): (200, [{"order_id": "o777"}]),
            },
            captured,
        )
        adapter = self._adapter()
        _attach(adapter, handler, "https://localhost:5000")
        ack = await adapter.submit_order(_intent(order_type=OrderType.LIMIT,
                                                 limit_price=Decimal("2950")))
        assert ack.broker_order_id == "o777"
        assert adapter._tracked["o777"] == "cid-1"
        import json as _json
        body = _json.loads(captured[0].content.decode())
        assert body["orders"][0]["conid"] == 2885
        assert body["orders"][0]["orderType"] == "LMT"

    async def test_submit_direct_order_id(self) -> None:
        handler = _router(
            {("POST", "/v1/api/iserver/account/DU123/orders"): (200, [{"order_id": "o1"}])}, []
        )
        adapter = self._adapter()
        _attach(adapter, handler, "https://localhost:5000")
        ack = await adapter.submit_order(_intent())
        assert ack.broker_order_id == "o1"

    async def test_rejected_submit_raises(self) -> None:
        handler = _router(
            {("POST", "/v1/api/iserver/account/DU123/orders"): (400, {"error": "no"})}, []
        )
        adapter = self._adapter()
        _attach(adapter, handler, "https://localhost:5000")
        with pytest.raises(ConflictError):
            await adapter.submit_order(_intent())

    async def test_stream_normalizes_partial_fill(self) -> None:
        adapter = self._adapter()
        adapter._tracked["o9"] = "cid-9"
        handler = _router(
            {("GET", "/v1/api/iserver/account/orders"): (
                200,
                {"orders": [{"orderId": "o9", "status": "Submitted",
                             "filledQuantity": 4, "avgPrice": 100.25}]},
            )},
            [],
        )
        _attach(adapter, handler, "https://localhost:5000")
        update = await _first_update(adapter)
        assert update.status is OrderStatus.PARTIALLY_FILLED
        assert update.filled_quantity == Decimal("4")

    async def test_balances_from_ledger(self) -> None:
        handler = _router(
            {("GET", "/v1/api/portfolio/DU123/ledger"): (
                200, {"USD": {"cashbalance": 12500.5}, "BASE": {"cashbalance": 12500.5}},
            )},
            [],
        )
        adapter = self._adapter()
        _attach(adapter, handler, "https://localhost:5000")
        balances = await adapter.get_balances()
        assert balances["USD"] == Decimal("12500.5")
