"""Production must fail fast rather than degrade quietly.

Two behaviours are pinned here:

* Starting ``ENVIRONMENT=production`` without a database, an agent credential or
  a dashboard credential must raise, not fall back. The pre-Phase-2 production
  deployment ran with ``DATABASE_URL=""`` — telemetry in RAM, deduplication off,
  everything lost on restart — and looked perfectly healthy while doing it.

* A transient store failure must surface as 503, so the agent's durable queue
  holds the batch and retries. Answering 200 would make the agent delete
  envelopes the server never persisted (``raj_monitor/agent.py::_drain_once``
  only deletes queue rows after a successful upload).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

from app.core.config import Settings

BACKEND_DIR = Path(__file__).resolve().parents[1]

_PROD = {
    "ENVIRONMENT": "production",
    "DATABASE_URL": "postgresql+psycopg://u:p@db:5432/ops",
    "RAJ_AGENT_TOKEN": "prod-agent-token",
    "RAJ_DASHBOARD_TOKEN": "prod-dashboard-token",
}


def _settings(**overrides: str | None) -> Settings:
    values = {**_PROD, **overrides}
    return Settings(**{k.lower(): v for k, v in values.items() if v is not None})


# --------------------------------------------------------------------------- #
# Fail-fast configuration guard
# --------------------------------------------------------------------------- #
def test_production_with_full_configuration_is_accepted() -> None:
    _settings().assert_production_ready()  # must not raise


def test_production_without_database_refuses_to_start() -> None:
    with pytest.raises(RuntimeError) as excinfo:
        _settings(DATABASE_URL=None).assert_production_ready()
    assert "DATABASE_URL" in str(excinfo.value)


def test_production_with_empty_database_url_refuses_to_start() -> None:
    """`DATABASE_URL=""` is exactly what the old manifests shipped."""
    with pytest.raises(RuntimeError):
        _settings(DATABASE_URL="").assert_production_ready()


def test_production_without_agent_token_refuses_to_start() -> None:
    with pytest.raises(RuntimeError) as excinfo:
        _settings(RAJ_AGENT_TOKEN=None).assert_production_ready()
    assert "RAJ_AGENT_TOKEN" in str(excinfo.value)


def test_production_without_dashboard_token_refuses_to_start() -> None:
    with pytest.raises(RuntimeError) as excinfo:
        _settings(RAJ_DASHBOARD_TOKEN=None).assert_production_ready()
    assert "websocket" in str(excinfo.value).lower()


def test_production_error_reports_every_problem_at_once() -> None:
    """One restart should reveal all misconfigurations, not one per attempt."""
    with pytest.raises(RuntimeError) as excinfo:
        _settings(DATABASE_URL=None, RAJ_AGENT_TOKEN=None,
                  RAJ_DASHBOARD_TOKEN=None).assert_production_ready()
    message = str(excinfo.value)
    assert "DATABASE_URL" in message
    assert "RAJ_AGENT_TOKEN" in message
    assert "websocket" in message.lower()


def test_production_failure_message_contains_no_secrets() -> None:
    with pytest.raises(RuntimeError) as excinfo:
        _settings(DATABASE_URL=None).assert_production_ready()
    assert "prod-agent-token" not in str(excinfo.value)
    assert "prod-dashboard-token" not in str(excinfo.value)


def test_non_production_still_allows_mock_mode() -> None:
    """Local development keeps working without any of this configuration."""
    Settings(environment="development").assert_production_ready()  # must not raise


def test_production_startup_actually_aborts() -> None:
    """End-to-end: the process exits rather than serving a bad configuration."""
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(BACKEND_DIR), env.get("PYTHONPATH", "")) if part
    )
    env["ENVIRONMENT"] = "production"
    env["DATABASE_URL"] = ""
    for key in ("RAJ_AGENT_TOKEN", "RAJ_AGENT_TOKENS", "RAJ_DASHBOARD_TOKEN"):
        env.pop(key, None)

    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent("""
            try:
                import main  # noqa: F401
            except RuntimeError as exc:
                print("REFUSED:" + str(exc).replace(chr(10), " | "))
            else:
                print("STARTED")
        """)],
        cwd=BACKEND_DIR, env=env, check=True, capture_output=True, text=True, timeout=120,
    )
    output = result.stdout.strip().splitlines()[-1]
    assert output.startswith("REFUSED:"), output
    assert "DATABASE_URL" in output


# --------------------------------------------------------------------------- #
# Transient failure -> 503 (agent retries) rather than 200 (agent discards)
# --------------------------------------------------------------------------- #
def _run(code: str, database_url: str) -> dict:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(BACKEND_DIR), env.get("PYTHONPATH", "")) if part
    )
    env["DATABASE_URL"] = database_url
    env["RAJ_AGENT_TOKEN"] = "transient-token"
    env["RAJ_DASHBOARD_TOKEN"] = "transient-dashboard"
    env.pop("RAJ_AGENT_TOKENS", None)
    env.pop("ENVIRONMENT", None)
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=BACKEND_DIR, env=env, check=True, capture_output=True, text=True, timeout=120,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.fixture
def database(tmp_path: Path) -> str:
    url = f"sqlite:///{(tmp_path / 'transient.db').as_posix()}"
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(BACKEND_DIR), env.get("PYTHONPATH", "")) if part
    )
    env["DATABASE_URL"] = url
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                   cwd=BACKEND_DIR, env=env, check=True, capture_output=True,
                   text=True, timeout=120)
    return url


def test_transient_store_failure_returns_503_not_200(database: str) -> None:
    """A database error must not be acknowledged as success."""
    result = _run("""
        import json
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from sqlalchemy.exc import OperationalError
        from main import app

        HEADERS = {"X-Raj-Agent-Token": "transient-token", "X-Raj-Agent-Id": "a1"}
        boom = OperationalError("SELECT 1", {}, Exception("connection lost"))

        with TestClient(app) as c:
            with patch("app.services.agent_service.reserve_envelope", side_effect=boom):
                r = c.post("/api/agent/batch", json={
                    "agentId": "a1", "machine": "gcp-trading-01",
                    "items": [{"id": "t-1", "kind": "event", "machine": "gcp-trading-01",
                               "data": {"message": "x"}}],
                }, headers=HEADERS)
        print(json.dumps({"status": r.status_code}))
        """, database)
    assert result["status"] == 503, "a transient failure must tell the agent to retry"


def test_transient_failure_is_not_dead_lettered(database: str) -> None:
    """Dead-lettering a recoverable envelope would destroy retrievable data."""
    result = _run("""
        import json
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from sqlalchemy.exc import OperationalError
        from main import app
        from app.repositories import dead_letter_repo

        HEADERS = {"X-Raj-Agent-Token": "transient-token", "X-Raj-Agent-Id": "a1"}
        boom = OperationalError("SELECT 1", {}, Exception("connection lost"))

        with TestClient(app) as c:
            with patch("app.services.agent_service.reserve_envelope", side_effect=boom):
                c.post("/api/agent/batch", json={
                    "agentId": "a1", "machine": "gcp-trading-01",
                    "items": [{"id": "t-2", "kind": "event", "machine": "gcp-trading-01",
                               "data": {"message": "x"}}],
                }, headers=HEADERS)
        print(json.dumps({"dead_letters": len(dead_letter_repo.list())}))
        """, database)
    assert result["dead_letters"] == 0


def test_recovery_after_transient_failure_persists_the_data(database: str) -> None:
    """The retried batch lands once the store recovers — nothing is lost."""
    result = _run("""
        import json
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from sqlalchemy.exc import OperationalError
        from main import app
        from app.repositories import events_repo

        HEADERS = {"X-Raj-Agent-Token": "transient-token", "X-Raj-Agent-Id": "a1"}
        boom = OperationalError("SELECT 1", {}, Exception("connection lost"))
        payload = {"agentId": "a1", "machine": "gcp-trading-01",
                   "items": [{"id": "t-3", "kind": "event", "machine": "gcp-trading-01",
                              "strategy": "S5-10",
                              "data": {"category": "strategy", "severity": "info",
                                       "message": "recovered"}}]}

        with TestClient(app) as c:
            with patch("app.services.agent_service.reserve_envelope", side_effect=boom):
                first = c.post("/api/agent/batch", json=payload, headers=HEADERS)
            second = c.post("/api/agent/batch", json=payload, headers=HEADERS)
        print(json.dumps({
            "first": first.status_code, "second": second.status_code,
            "processed": second.json()["processed"], "events": len(events_repo.list()),
        }))
        """, database)
    assert result["first"] == 503
    assert result["second"] == 200
    assert result["processed"] == 1
    assert result["events"] == 1
