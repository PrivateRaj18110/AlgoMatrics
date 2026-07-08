"""Agent contract test: the simulator plugin satisfies the MT5 adapter's shape."""

from __future__ import annotations

from decimal import Decimal

import pytest
from algo_agent.main import create_app
from algo_agent.plugins import OrderRequest, SimulatorPlugin
from fastapi.testclient import TestClient


def test_simulator_market_order_fills_and_moves_position() -> None:
    plugin = SimulatorPlugin(mark_price=Decimal("100"))
    order = plugin.submit(
        OrderRequest(
            client_order_id="c-1",
            symbol="EURUSD",
            side="buy",
            order_type="market",
            volume=Decimal("2"),
        )
    )
    assert order.status == "filled"
    assert order.filled_volume == Decimal("2")
    positions = plugin.positions()
    assert positions == [{"symbol": "EURUSD", "volume": "2"}]


def test_health_and_order_roundtrip_over_http() -> None:
    app = create_app(SimulatorPlugin())
    client = TestClient(app)

    health = client.get("/health").json()
    assert health["terminal_connected"] is True

    response = client.post(
        "/orders",
        json={
            "client_order_id": "c-2",
            "symbol": "GBPUSD",
            "side": "sell",
            "order_type": "market",
            "volume": "1",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "filled"
    assert body["client_order_id"] == "c-2"

    orders = client.get("/orders").json()["orders"]
    assert len(orders) == 1

    account = client.get("/account").json()
    assert "balance" in account


def test_token_auth_rejects_bad_bearer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_TOKEN", "s3cret")
    app = create_app(SimulatorPlugin())
    client = TestClient(app)
    # No token → 401 on a protected route.
    assert client.get("/orders").status_code == 401
    # Correct token → 200.
    ok = client.get("/orders", headers={"Authorization": "Bearer s3cret"})
    assert ok.status_code == 200


def test_production_agent_fails_closed_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_ENV", "production")
    monkeypatch.delenv("AGENT_TOKEN", raising=False)
    client = TestClient(create_app(SimulatorPlugin()))

    assert client.get("/health").status_code == 503
    assert client.get("/orders").status_code == 503
