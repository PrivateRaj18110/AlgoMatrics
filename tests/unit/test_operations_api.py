from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
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


def test_historical_demo_seed_data_is_excluded_from_operations_api() -> None:
    from tests.unit.operations_sqlite import insert_demo_seed_data

    with ops_sqlite_db("_tmp_ops_demo_filter.db") as url:
        insert_mixed_batch(url)
        insert_demo_seed_data(url)
        service = OperationsService(TelemetryStore(url), app_env="test")
        client = TestClient(_app(service))

        # Machines: only real GCP machine, London VPS / Personal Computer excluded
        machines = client.get("/api/v1/operations/machines").json()
        assert len(machines) == 1
        assert machines[0]["id"] == "mch-gcp-1"
        assert machines[0]["name"] == "gcp-trading-1"
        machine_names = {m["name"] for m in machines}
        assert "London VPS" not in machine_names
        assert "Personal Computer" not in machine_names

        # Trades: only real trade (Alpha), Mean Reversion FX / Gold Scalper excluded
        trades = client.get("/api/v1/operations/trades").json()
        assert len(trades) == 1
        assert trades[0]["strategy"] == "Alpha"
        trade_strategies = {t["strategy"] for t in trades}
        assert "Mean Reversion FX" not in trade_strategies
        assert "Gold Scalper" not in trade_strategies

        # Strategies & Analytics: no demo strategies or fixtures
        strategies = client.get("/api/v1/operations/strategies").json()
        assert [row["strategy_name"] for row in strategies] == ["Alpha"]

        analytics = client.get("/api/v1/operations/analytics").json()
        for name in FIXTURE_NAMES:
            assert name not in str(analytics)

        # Overview: counts 1 real machine, not 3
        overview = client.get("/api/v1/operations/overview").json()
        assert overview["machine_count"] == 1
        # Heartbeat is aged (2026-08-17), so derived status is offline
        assert overview["online_machines"] == 0
        assert overview["closed_trade_count"] == 1

        service._store.close()


def test_real_trade_with_null_envelope_id_remains_visible() -> None:
    """A real trade on a real machine must remain visible even if envelope_id is NULL."""
    from datetime import UTC, datetime

    from sqlalchemy import create_engine, text
    from tests.unit.operations_sqlite import insert_demo_seed_data

    now = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
    with ops_sqlite_db("_tmp_ops_null_envelope.db") as url:
        insert_demo_seed_data(url)
        engine = create_engine(url, future=True)
        with engine.begin() as conn:
            # Insert real Google machine
            conn.execute(
                text(
                    """
                    INSERT OR IGNORE INTO machines (
                        id, name, status, live, hostname, last_heartbeat,
                        last_successful_upload, queue_depth, created_at, updated_at
                    ) VALUES (
                        'mch-agent-gcp-2', 'gcp-trading-2', 'online', 1,
                        'gcp-trading-2', :hb, :hb, 0, :hb, :hb
                    )
                    """
                ),
                {"hb": now},
            )
            # Insert a real trade on real machine with envelope_id = NULL
            conn.execute(
                text(
                    """
                    INSERT OR IGNORE INTO trades (
                        id, envelope_id, time, strategy, machine, machine_id,
                        broker, account, symbol, direction, entry, exit,
                        quantity, pnl, latency_ms, duration_sec, status, created_at
                    ) VALUES (
                        'trd-real-no-env', NULL, :time, 'Trend Alpha',
                        'gcp-trading-2', 'mch-agent-gcp-2', 'Zerodha',
                        'ACC-9999', 'NIFTY', 'long', 24000, 24100, 50,
                        5000.0, 10, 120, 'closed', :time
                    )
                    """
                ),
                {"time": now},
            )
        engine.dispose()

        service = OperationsService(TelemetryStore(url), app_env="test")
        client = TestClient(_app(service))

        # Real trade with envelope_id = NULL is present
        trades = client.get("/api/v1/operations/trades").json()
        assert len(trades) == 1
        assert trades[0]["id"] == "trd-real-no-env"
        assert trades[0]["strategy"] == "Trend Alpha"
        assert trades[0]["machine_id"] == "mch-agent-gcp-2"

        # Strategies reflects the real trade
        strategies = client.get("/api/v1/operations/strategies").json()
        assert [row["strategy_name"] for row in strategies] == ["Trend Alpha"]

        # Demo trades from insert_demo_seed_data are excluded
        trade_strategies = {t["strategy"] for t in trades}
        assert "Mean Reversion FX" not in trade_strategies
        assert "Gold Scalper" not in trade_strategies

        service._store.close()


def test_historical_closed_trades_pnl_and_offline_strategy_status() -> None:
    """Historical closed trades contribute to recorded PnL while offline hosts report offline."""
    with ops_sqlite_db("_tmp_ops_historical.db") as url:
        engine = create_engine(url, future=True)
        with engine.begin() as conn:
            # Insert historical machine with expired heartbeat (>120s ago)
            stale_hb = datetime(2026, 8, 17, 10, 0, tzinfo=UTC)
            conn.execute(
                text(
                    """
                    INSERT INTO machines (
                        id, name, status, live, hostname, last_heartbeat,
                        last_successful_upload, queue_depth, created_at, updated_at
                    ) VALUES (
                        'mch-agent-gcp-hist', 'gcp-trading-hist', 'online', 1,
                        'gcp-trading-hist', :hb, :hb, 0, :hb, :hb
                    )
                    """
                ),
                {"hb": stale_hb},
            )
            # Insert historical strategy status event
            conn.execute(
                text(
                    """
                    INSERT INTO events (
                        id, envelope_id, time, category, severity, source, message,
                        machine_id, event_type, strategy, symbol, payload_summary, created_at
                    ) VALUES (
                        'evt-hist-ss', 'env-hist-ss', :time, 'telemetry', 'info', 'agent',
                        'running', 'mch-agent-gcp-hist', 'strategy_status', 'NiftyTrend',
                        'NIFTY', 'running', :time
                    )
                    """
                ),
                {"time": stale_hb},
            )
            # Insert historical closed trade
            conn.execute(
                text(
                    """
                    INSERT INTO trades (
                        id, envelope_id, time, strategy, machine, machine_id,
                        broker, account, symbol, direction, entry, exit,
                        quantity, pnl, latency_ms, duration_sec, status, created_at
                    ) VALUES (
                        'trd-hist-1', 'env-hist-trd', :time, 'NiftyTrend',
                        'gcp-trading-hist', 'mch-agent-gcp-hist', 'Zerodha',
                        'ACC-1234', 'NIFTY 24500 CE', 'long', 150.0, 180.0,
                        50, 1500.0, 12, 180, 'closed', :time
                    )
                    """
                ),
                {"time": stale_hb},
            )
        engine.dispose()

        service = OperationsService(TelemetryStore(url), app_env="test")
        client = TestClient(_app(service))

        # 1. Overview reflects recorded machines and historical PnL
        overview = client.get("/api/v1/operations/overview").json()
        assert overview["machine_count"] == 1
        assert overview["online_machines"] == 0  # Offline due to expired heartbeat
        assert overview["closed_trade_count"] == 1
        assert overview["total_pnl"] == 1500.0

        # 2. Machine endpoint reports offline
        machines = client.get("/api/v1/operations/machines").json()
        assert len(machines) == 1
        assert machines[0]["status"] == "offline"

        # 3. Strategies endpoint reports offline (not running)
        strategies = client.get("/api/v1/operations/strategies").json()
        assert len(strategies) == 1
        assert strategies[0]["strategy_name"] == "NiftyTrend"
        assert strategies[0]["status"] == "offline"
        assert strategies[0]["trade_count"] == 1
        assert strategies[0]["total_pnl"] == 1500.0

        service._store.close()


def test_historical_international_trades_and_postgres_boolean_filtering() -> None:
    """Historical international trades remain visible while suspect placeholders are excluded."""
    with ops_sqlite_db("_tmp_ops_intl_hist.db") as url:
        engine = create_engine(url, future=True)
        with engine.begin() as conn:
            now = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
            # 1. Real live=1 machine vs demo live=0 machine
            conn.execute(
                text(
                    """
                    INSERT INTO machines (
                        id, name, status, live, hostname, last_heartbeat,
                        last_successful_upload, queue_depth, created_at, updated_at
                    ) VALUES (
                        'mch-agent-gcp-1', 'gcp-trading-1', 'online', 1,
                        'gcp-trading-1', :hb, :hb, 0, :hb, :hb
                    ), (
                        'mch-london', 'London VPS', 'offline', 0,
                        'london-vps', :hb, :hb, 0, :hb, :hb
                    )
                    """
                ),
                {"hb": now},
            )
            # 2. Historical trade on IC Markets with real PnL
            conn.execute(
                text(
                    """
                    INSERT INTO trades (
                        id, envelope_id, time, strategy, machine, machine_id,
                        broker, account, symbol, direction, entry, exit,
                        quantity, pnl, latency_ms, duration_sec, status, created_at
                    ) VALUES (
                        'trd-0033', 'env-hist-1', :time, 'Stat Arb Pairs',
                        'London VPS', 'mch-agent-gcp-1', 'IC Markets',
                        'LIVE-003', 'NAS100', 'long', 18729.1, 18770.8,
                        1, 179.0, 15, 13174, 'closed', :time
                    )
                    """
                ),
                {"time": now},
            )
            # 3. Suspect placeholder row (should be excluded)
            conn.execute(
                text(
                    """
                    INSERT INTO trades (
                        id, envelope_id, time, strategy, machine, machine_id,
                        broker, account, symbol, direction, entry, exit,
                        quantity, pnl, latency_ms, duration_sec, status, created_at
                    ) VALUES (
                        'trd-ph-1', 'env-ph-1', :time, '',
                        'gcp-trading-1', 'mch-agent-gcp-1', '',
                        '', '', 'long', 0, NULL,
                        0, 0, 0, 0, 'closed', :time
                    )
                    """
                ),
                {"time": now},
            )
        engine.dispose()

        service = OperationsService(TelemetryStore(url), app_env="test")
        client = TestClient(_app(service))

        # Machines: Only live=1 machine returned
        machines = client.get("/api/v1/operations/machines").json()
        assert len(machines) == 1
        assert machines[0]["id"] == "mch-agent-gcp-1"

        # Trades: Historical IC Markets trade is returned, placeholder is excluded
        trades = client.get("/api/v1/operations/trades").json()
        assert len(trades) == 1
        assert trades[0]["id"] == "trd-0033"
        assert trades[0]["broker"] == "IC Markets"
        assert trades[0]["pnl"] == 179.0

        # Overview: PnL reflects the historical trade
        overview = client.get("/api/v1/operations/overview").json()
        assert overview["closed_trade_count"] == 1
        assert overview["total_pnl"] == 179.0

        service._store.close()


def test_system_health_endpoint_empty_when_no_data() -> None:
    with ops_sqlite_db("ops_health_empty.db") as url:
        service = OperationsService(TelemetryStore(url), app_env="test")
        client = TestClient(_app(service))

        res = client.get("/api/v1/operations/system-health")
        assert res.status_code == 200
        data = res.json()
        assert data["points"] == []
        assert data["is_live"] is False
        assert data["current_execution_status"] == "offline"

        # /api/v1/operations/health alias works identically
        res_alias = client.get("/api/v1/operations/health")
        assert res_alias.status_code == 200
        assert res_alias.json()["points"] == []

        service._store.close()


def test_system_health_endpoint_with_real_points() -> None:
    with ops_sqlite_db("ops_health_real.db") as url:
        now = datetime.now(UTC)
        engine = create_engine(url, future=True)
        with engine.begin() as conn:
            # 1. Insert real machine (online)
            conn.execute(
                text(
                    """
                    INSERT INTO machines (
                        id, name, location, provider, status, cpu, ram, disk,
                        internet_ms, broker_ping_ms, python_status, uptime_sec,
                        last_heartbeat, strategy_count, live, hostname, created_at, updated_at
                    ) VALUES (
                        'mch-agent-google-vm-raj-quant-server', 'google-vm-raj-quant-server',
                        'GCP Asia', 'GCP', 'online', 15.0, 30.0, 45.0,
                        2.0, 5.0, 'online', 3600,
                        :time, 2, 1, 'google-vm-raj-quant-server', :time, :time
                    )
                    """
                ),
                {"time": now},
            )
            # 2. Insert system health snapshot
            conn.execute(
                text(
                    """
                    INSERT INTO system_health_snapshots (
                        id, machine_id, agent_id, event_id, timestamp_utc,
                        tick_rate, tick_delay_ms, queue_size, queue_wait_ms,
                        avg_latency_ms, p95_latency_ms, p99_latency_ms,
                        api_success_pct, signal_fill_rate_pct, cpu_usage_pct,
                        memory_mb, status, created_at
                    ) VALUES (
                        'hlth-001', 'mch-agent-google-vm-raj-quant-server',
                        'google-vm-data-agent', 'evt-001', :time,
                        18.5, 0.4, 1, 2.5,
                        6.2, 7.8, 8.9,
                        100.0, 95.0, 14.5,
                        210.0, 'STABLE', :time
                    )
                    """
                ),
                {"time": now},
            )
        engine.dispose()

        service = OperationsService(TelemetryStore(url), app_env="test")
        client = TestClient(_app(service))

        res = client.get(
            "/api/v1/operations/system-health?machine_id=mch-agent-google-vm-raj-quant-server"
        )
        assert res.status_code == 200
        data = res.json()
        assert data["machine_id"] == "mch-agent-google-vm-raj-quant-server"
        assert data["is_live"] is True
        assert data["current_execution_status"] == "online"
        assert data["current_health_status"] == "STABLE"
        assert len(data["points"]) == 1

        pt = data["points"][0]
        assert pt["tick_rate"] == 18.5
        assert pt["tick_delay_ms"] == 0.4
        assert pt["queue_size"] == 1
        assert pt["queue_wait_ms"] == 2.5
        assert pt["avg_latency_ms"] == 6.2
        assert pt["p95_latency_ms"] == 7.8
        assert pt["p99_latency_ms"] == 8.9
        assert pt["api_success_pct"] == 100.0
        assert pt["signal_fill_rate_pct"] == 95.0
        assert pt["cpu_usage_pct"] == 14.5
        assert pt["memory_mb"] == 210.0
        assert pt["status"] == "STABLE"
        assert pt["timestamp"].endswith("Z")

        service._store.close()





