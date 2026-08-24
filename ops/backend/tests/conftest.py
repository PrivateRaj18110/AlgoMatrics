"""Shared fixtures for the ops backend suite.

``get_settings`` is ``lru_cache``d, so any test that changes ingestion
credentials must clear it — otherwise the first test to touch settings pins the
configuration for the whole session.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings

FLEET_TOKEN = "test-fleet-token-do-not-use-in-production"
SCOPED_TOKEN = "test-scoped-token-do-not-use-in-production"
SCOPED_MACHINE = "gcp-trading-01"
DASHBOARD_TOKEN = "test-dashboard-token-do-not-use-in-production"


def _reset_settings() -> None:
    get_settings.cache_clear()


@pytest.fixture
def configure_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Set ingestion credentials for the duration of one test."""
    monkeypatch.setenv("RAJ_AGENT_TOKEN", FLEET_TOKEN)
    monkeypatch.setenv("RAJ_AGENT_TOKENS", f"{SCOPED_MACHINE}:{SCOPED_TOKEN}")
    monkeypatch.setenv("RAJ_DASHBOARD_TOKEN", DASHBOARD_TOKEN)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("OPS_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _reset_settings()
    yield
    _reset_settings()


@pytest.fixture
def unconfigured_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Remove every ingestion credential — the fail-closed case."""
    for key in ("RAJ_AGENT_TOKEN", "RAJ_AGENT_TOKENS", "RAJ_DASHBOARD_TOKEN",
                "OPS_JWT_PUBLIC_KEY", "OPS_DATABASE_URL", "DATABASE_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    _reset_settings()
    yield
    _reset_settings()


@pytest.fixture
def client(configure_env: None) -> Iterator[TestClient]:
    from main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def anon_client(unconfigured_env: None) -> Iterator[TestClient]:
    from main import app

    with TestClient(app) as test_client:
        yield test_client


def agent_headers(token: str = FLEET_TOKEN, agent_id: str = "agent-test-0001") -> dict[str, str]:
    return {"X-Raj-Agent-Token": token, "X-Raj-Agent-Id": agent_id}


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Keep a developer's real .env out of the suite."""
    os.environ.setdefault("APP_NAME", "Raj Quant OS API (test)")
    yield
