from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.unit.operations_sqlite import insert_mixed_batch, ops_sqlite_db

from algo_platform.api.middleware.errors import register_exception_handlers
from algo_platform.modules.operations.application.service import OperationsService
from algo_platform.modules.operations.infrastructure.telemetry_store import TelemetryStore
from algo_platform.modules.operations.presentation.router import (
    get_operations_service,
    require_ops_read,
    router,
)
from algo_platform.shared.domain.errors import AuthenticationFailed, UnavailableError

FIXTURE_NAMES = (
    "Mean Reversion FX",
    "Gold Scalper",
    "Momentum Breakout",
    "IC Markets",
    "Binance",
    "London VPS",
)


def _app(service: OperationsService) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")

    async def _tenant():
        return object()

    def _service() -> OperationsService:
        return service

    app.dependency_overrides[require_ops_read] = _tenant
    app.dependency_overrides[get_operations_service] = _service
    return app


def test_operations_requires_authentication() -> None:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router, prefix="/api/v1")

    async def deny():
        raise AuthenticationFailed("authentication required")

    app.dependency_overrides[require_ops_read] = deny
    client = TestClient(app)
    response = client.get("/api/v1/operations/machines")
    assert response.status_code == 401


def test_missing_ops_url_is_empty_outside_production() -> None:
    service = OperationsService(TelemetryStore(None), app_env="local")
    assert service.machines() == []
    assert service.closed_trades() == []
    assert service.strategies() == []
    payload = service.analytics()
    for name in FIXTURE_NAMES:
        assert name not in str(payload)


def test_missing_ops_url_fails_closed_in_production() -> None:
    service = OperationsService(TelemetryStore(None), app_env="production")
    try:
        service.machines()
        raise AssertionError("expected UnavailableError")
    except UnavailableError:
        pass
    client = TestClient(_app(service))
    response = client.get("/api/v1/operations/machines")
    assert response.status_code == 503


def test_configured_sqlite_endpoints() -> None:
    with ops_sqlite_db("_tmp_ops_api.db") as url:
        insert_mixed_batch(url)
        service = OperationsService(TelemetryStore(url), app_env="test")
        client = TestClient(_app(service))

        machines = client.get("/api/v1/operations/machines").json()
        assert machines[0]["id"] == "mch-gcp-1"
        assert machines[0]["name"] != "London VPS"

        events = client.get("/api/v1/operations/events").json()
        types = {row["event_type"] for row in events}
        assert types == {
            "heartbeat",
            "strategy_status",
            "system_status",
            "order",
            "trade_closed",
        }

        heartbeats = client.get(
            "/api/v1/operations/events", params={"event_type": "heartbeat"}
        ).json()
        assert len(heartbeats) == 1

        page = client.get("/api/v1/operations/events", params={"limit": 2, "offset": 0}).json()
        assert len(page) == 2
        page2 = client.get("/api/v1/operations/events", params={"limit": 2, "offset": 2}).json()
        assert len(page2) == 2

        trades = client.get("/api/v1/operations/trades").json()
        assert len(trades) == 1
        assert trades[0]["strategy"] == "Alpha"
        assert trades[0]["entry"] == 100.5
        assert str(trades[0]["time"]).endswith("Z")

        filtered = client.get(
            "/api/v1/operations/trades",
            params={
                "direction": "long",
                "status": "closed",
                "strategy": "Alpha",
                "symbol": "NIFTY",
            },
        ).json()
        assert len(filtered) == 1
        assert client.get("/api/v1/operations/trades", params={"direction": "short"}).json() == []

        strategies = client.get("/api/v1/operations/strategies").json()
        assert [row["strategy_name"] for row in strategies] == ["Alpha"]
        assert strategies[0]["trade_count"] == 1
        assert strategies[0]["winning_trades"] == 1
        assert "NIFTY" in strategies[0]["symbols"]

        analytics = client.get("/api/v1/operations/analytics").json()
        assert analytics["symbols"][0]["symbol"] == "NIFTY"
        assert analytics["by_symbol"][0]["strategy_name"] == "Alpha"
        for name in FIXTURE_NAMES:
            assert name not in str(analytics)

        alerts = client.get("/api/v1/operations/alerts").json()
        assert alerts == []
        orders = client.get("/api/v1/operations/orders").json()
        assert len(orders) == 1
        assert orders[0]["event_type"] == "order"
        service._store.close()
