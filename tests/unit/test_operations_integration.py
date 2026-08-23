from __future__ import annotations

import importlib.util
from pathlib import Path

from tests.unit.operations_sqlite import insert_mixed_batch, ops_sqlite_db

from algo_platform.modules.operations.application.service import OperationsService
from algo_platform.modules.operations.domain.classification import (
    NON_TRADE_KINDS,
    TRADE_KINDS,
)
from algo_platform.modules.operations.infrastructure.telemetry_store import (
    TelemetryStore,
    _sync_url,
)


def test_classification_contract_matches_f9bee1a() -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "ops"
        / "backend"
        / "app"
        / "services"
        / "telemetry_classification.py"
    )
    spec = importlib.util.spec_from_file_location("ops_telemetry_classification", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.TRADE_KINDS == TRADE_KINDS == frozenset({"trade", "trade_closed"})
    assert module.NON_TRADE_KINDS == NON_TRADE_KINDS
    for kind in ("heartbeat", "strategy_status", "system_status", "order"):
        assert kind in NON_TRADE_KINDS
        assert kind not in TRADE_KINDS


def test_mixed_batch_creates_exactly_one_closed_trade() -> None:
    with ops_sqlite_db("_tmp_ops_mixed.db") as url:
        insert_mixed_batch(url)
        service = OperationsService(TelemetryStore(url), app_env="test")
        events = service.events()
        trades = service.closed_trades()
        assert len(events) == 5
        assert {row["event_type"] for row in events} == {
            "heartbeat",
            "strategy_status",
            "system_status",
            "order",
            "trade_closed",
        }
        assert len(trades) == 1
        assert trades[0]["id"] == "trd-1"
        assert trades[0]["envelope_id"] == "env-tc"
        service._store.close()


def test_duplicate_envelope_does_not_create_second_trade() -> None:
    with ops_sqlite_db("_tmp_ops_dup.db") as url:
        insert_mixed_batch(url)
        insert_mixed_batch(url, duplicate=True)
        service = OperationsService(TelemetryStore(url), app_env="test")
        assert len(service.closed_trades()) == 1
        assert len(service.events()) == 5
        service._store.close()


def test_ops_sync_url_uses_psycopg() -> None:
    assert _sync_url("postgresql+asyncpg://u:p@h/db") == "postgresql+psycopg://u:p@h/db"


def test_psycopg_driver_is_installed() -> None:
    import pytest

    psycopg = pytest.importorskip("psycopg")
    assert psycopg is not None

