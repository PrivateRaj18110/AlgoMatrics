"""Regression coverage for the two production release blockers."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

from sqlalchemy import create_engine

from app.core.config import Settings


BACKEND_DIR = Path(__file__).resolve().parents[1]


def _environment(database_url: str | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(BACKEND_DIR), env.get("PYTHONPATH", "")) if part
    )
    if database_url is None:
        env.pop("DATABASE_URL", None)
    else:
        env["DATABASE_URL"] = database_url
    return env


def _run_backend(code: str, database_url: str | None = None) -> dict:
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=BACKEND_DIR,
        env=_environment(database_url),
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def _migrate(database_url: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=_environment(database_url),
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_mock_mode_still_starts_and_serves_data() -> None:
    result = _run_backend(
        """
        import json
        from fastapi.testclient import TestClient
        from app.database.session import database_enabled
        from app.repositories import events_repo
        from main import app

        with TestClient(app) as client:
            health = client.get("/api/health")
            events = client.get("/api/events")
        print(json.dumps({
            "database_enabled": database_enabled(),
            "repository": type(events_repo).__name__,
            "health": health.status_code,
            "events": events.status_code,
        }))
        """
    )
    assert result == {
        "database_enabled": False,
        "repository": "EventsRepository",
        "health": 200,
        "events": 200,
    }


def test_sqlite_mode_starts_after_alembic_migration(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'raj.db').as_posix()}"
    _migrate(database_url)
    result = _run_backend(
        """
        import json
        from fastapi.testclient import TestClient
        from app.database.session import database_enabled, get_engine
        from main import app

        with TestClient(app) as client:
            health = client.get("/api/health")
            trades = client.get("/api/trades")
        print(json.dumps({
            "database_enabled": database_enabled(),
            "dialect": get_engine().dialect.name,
            "health": health.status_code,
            "trades": trades.status_code,
        }))
        """,
        database_url,
    )
    assert result == {
        "database_enabled": True,
        "dialect": "sqlite",
        "health": 200,
        "trades": 200,
    }


def test_standard_postgres_url_uses_psycopg_driver() -> None:
    settings = Settings(database_url="postgres://raj:secret@db.example.com:5432/quant")
    assert settings.database_url == "postgresql+psycopg://raj:secret@db.example.com:5432/quant"
    engine = create_engine(settings.database_url)
    try:
        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "psycopg"
    finally:
        engine.dispose()


def test_supabase_postgres_url_uses_psycopg_driver() -> None:
    raw = (
        "postgresql://postgres.project:p%40ss@aws-0-ap-south-1.pooler.supabase.com:"
        "6543/postgres?sslmode=require"
    )
    settings = Settings(database_url=raw)
    assert settings.database_url == raw.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(settings.database_url)
    try:
        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "psycopg"
    finally:
        engine.dispose()


def test_restart_safe_ids_and_envelope_idempotency(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'restart.db').as_posix()}"
    _migrate(database_url)
    first = _run_backend(
        """
        import asyncio
        import json
        from app.repositories import events_repo
        from app.schemas.agent import Envelope
        from app.services.agent_service import handle_events

        envelope = Envelope(
            id="restart-envelope-1", kind="event", machine="VPS-1", strategy="alpha",
            data={"category": "strategy", "severity": "info", "message": "first"},
        )
        asyncio.run(handle_events(envelope))
        rows = events_repo.list()
        print(json.dumps({"count": len(rows), "id": rows[0]["id"]}))
        """,
        database_url,
    )
    assert first["count"] == 1
    assert first["id"].startswith("evt-agent-")

    second = _run_backend(
        """
        import asyncio
        import json
        from app.repositories import events_repo
        from app.schemas.agent import Envelope
        from app.services.agent_service import handle_events

        duplicate = Envelope(
            id="restart-envelope-1", kind="event", machine="VPS-1", strategy="alpha",
            data={"category": "strategy", "severity": "info", "message": "duplicate"},
        )
        fresh = Envelope(
            id="restart-envelope-2", kind="event", machine="VPS-1", strategy="alpha",
            data={"category": "strategy", "severity": "info", "message": "fresh"},
        )
        asyncio.run(handle_events(duplicate))
        asyncio.run(handle_events(fresh))
        rows = events_repo.list()
        print(json.dumps({"count": len(rows), "ids": [row["id"] for row in rows]}))
        """,
        database_url,
    )
    assert second["count"] == 2
    assert len(set(second["ids"])) == 2
    assert first["id"] in second["ids"]


def test_websocket_notifications_and_api_contract_are_unchanged() -> None:
    result = _run_backend(
        """
        import json
        from fastapi.testclient import TestClient
        from main import app

        expected_paths = {
            "/", "/api/accounts", "/api/accounts/{account_id}", "/api/agent/batch",
            "/api/agent/events", "/api/agent/heartbeat", "/api/agent/logs",
            "/api/agent/metrics", "/api/agent/register", "/api/agent/trades",
            "/api/alerts", "/api/analytics", "/api/brokers", "/api/brokers/{broker_id}",
            "/api/dashboard/overview", "/api/events", "/api/execution/overview",
            "/api/health", "/api/ingest/error", "/api/ingest/event",
            "/api/ingest/heartbeat", "/api/ingest/metric", "/api/ingest/position",
            "/api/ingest/start", "/api/ingest/trade", "/api/logs", "/api/machines",
            "/api/machines/{machine_id}", "/api/risk/overview", "/api/settings",
            "/api/strategies", "/api/strategies/{strategy_id}", "/api/trades",
        }
        paths_unchanged = set(app.openapi()["paths"]) == expected_paths
        with TestClient(app) as client:
            with client.websocket_connect("/api/ws") as websocket:
                initial = websocket.receive_json()
                response = client.post("/api/agent/events", json={
                    "id": "ws-envelope-1", "kind": "event", "machine": "VPS-1",
                    "strategy": "alpha",
                    "data": {
                        "category": "strategy", "severity": "info",
                        "message": "websocket regression",
                    },
                })
                notification = websocket.receive_json()
        print(json.dumps({
            "paths_unchanged": paths_unchanged,
            "initial_type": initial["type"],
            "status": response.status_code,
            "response_keys": sorted(response.json()),
            "notification_type": notification["type"],
            "message": notification["payload"]["message"],
        }))
        """
    )
    assert result == {
        "paths_unchanged": True,
        "initial_type": "machines",
        "status": 200,
        "response_keys": ["accepted", "kind", "machineId", "processed", "received"],
        "notification_type": "event",
        "message": "websocket regression",
    }
