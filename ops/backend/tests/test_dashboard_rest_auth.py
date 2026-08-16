"""Dashboard REST authentication coverage."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from uuid import uuid4

import pytest
from app.api.dependencies.dashboard_auth import (
    extract_rest_credential,
    rest_auth_required,
)
from app.core.config import get_settings
from fastapi.testclient import TestClient

from tests.conftest import DASHBOARD_TOKEN, SCOPED_MACHINE, SCOPED_TOKEN, agent_headers


@pytest.fixture
def rest_auth_client(configure_env: None, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("OPS_REST_AUTH_REQUIRED", "true")
    get_settings.cache_clear()
    from main import app

    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


def _dashboard_headers(token: str = DASHBOARD_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _manifest(dataset_id: str) -> dict:
    content = b"rest auth manifest\n"
    return {
        "datasetId": dataset_id,
        "machine": SCOPED_MACHINE,
        "agentId": "agent-rest-auth",
        "sessionId": "2026-08-10-NSE",
        "tradingDate": "2026-08-10",
        "createdAt": "2026-08-10T16:01:00+00:00",
        "schemaVersion": "1",
        "files": [
            {
                "fileId": "ticks",
                "relativePath": "ticks/NIFTY.jsonl",
                "datasetType": "ticks",
                "sizeBytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "rowCount": 1,
            }
        ],
    }


def test_rest_auth_is_optional_in_dev_by_default(client: TestClient) -> None:
    response = client.get("/api/events")
    assert response.status_code == 200, response.text


def test_rest_read_requires_dashboard_credential_when_enabled(
    rest_auth_client: TestClient,
) -> None:
    response = rest_auth_client.get("/api/events")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_rest_read_accepts_authorization_bearer(rest_auth_client: TestClient) -> None:
    response = rest_auth_client.get("/api/events", headers=_dashboard_headers())
    assert response.status_code == 200, response.text


def test_rest_read_accepts_dashboard_token_header(rest_auth_client: TestClient) -> None:
    response = rest_auth_client.get(
        "/api/events",
        headers={"X-Raj-Dashboard-Token": DASHBOARD_TOKEN},
    )
    assert response.status_code == 200, response.text


def test_invalid_rest_credential_is_rejected_even_in_optional_mode(client: TestClient) -> None:
    response = client.get("/api/events", headers=_dashboard_headers("wrong-token"))
    assert response.status_code == 401


def test_health_stays_public_when_rest_auth_is_enabled(rest_auth_client: TestClient) -> None:
    response = rest_auth_client.get("/api/health")
    assert response.status_code == 200, response.text


def test_mixed_eod_read_routes_are_protected(rest_auth_client: TestClient) -> None:
    missing = rest_auth_client.get("/api/eod/reconciliation")
    accepted = rest_auth_client.get(
        "/api/eod/reconciliation",
        headers=_dashboard_headers(),
    )
    assert missing.status_code == 401
    assert accepted.status_code == 200, accepted.text


def test_eod_write_routes_keep_agent_auth_not_dashboard_auth(
    rest_auth_client: TestClient,
) -> None:
    dataset_id = f"rest-auth-{uuid4().hex[:12]}"

    dashboard_only = rest_auth_client.post(
        "/api/eod/manifests",
        json=_manifest(dataset_id),
        headers=_dashboard_headers(),
    )
    agent_write = rest_auth_client.post(
        "/api/eod/manifests",
        json=_manifest(dataset_id),
        headers=agent_headers(SCOPED_TOKEN),
    )

    assert dashboard_only.status_code == 401
    assert agent_write.status_code == 200, agent_write.text
    assert agent_write.json()["datasetId"] == dataset_id


def test_extract_rest_credential_supports_bearer_and_dashboard_header() -> None:
    assert extract_rest_credential("Bearer abc", None) == "abc"
    assert extract_rest_credential("Token abc", None) == "abc"
    assert extract_rest_credential("Basic abc", None) is None
    assert extract_rest_credential(None, " dashboard-token ") == "dashboard-token"


def test_production_implies_rest_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///ops.db")
    monkeypatch.setenv("RAJ_AGENT_TOKEN", "agent-token")
    monkeypatch.setenv("RAJ_DASHBOARD_TOKEN", "dashboard-token")
    get_settings.cache_clear()
    try:
        assert rest_auth_required() is True
    finally:
        get_settings.cache_clear()
