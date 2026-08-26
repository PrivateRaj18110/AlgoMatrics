"""Authentication coverage for the telemetry write path.

Before Phase 2 every ``/api/agent/*`` and ``/api/ingest/*`` route accepted any
caller, and the ops API was published at ``/ops/api``. These tests pin the
fail-closed behaviour that replaced it.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies.agent_auth import AgentPrincipal
from app.core.security import constant_time_equals, hash_token, token_matches
from tests.conftest import (
    DASHBOARD_TOKEN,
    FLEET_TOKEN,
    SCOPED_MACHINE,
    SCOPED_TOKEN,
    agent_headers,
)

# Every route that writes telemetry. Kept explicit rather than derived so a new
# unauthenticated route cannot slip past by simply not being discovered.
AGENT_ROUTES = [
    ("/api/agent/register", {"agentId": "a1", "machine": "m1"}),
    ("/api/agent/heartbeat", {"agentId": "a1", "machine": "m1"}),
    ("/api/agent/metrics", {"kind": "metrics", "machine": "m1"}),
    ("/api/agent/events", {"kind": "event", "machine": "m1", "data": {"message": "x"}}),
    ("/api/agent/trades", {"kind": "trade", "machine": "m1", "data": {"symbol": "X"}}),
    ("/api/agent/logs", {"kind": "log", "machine": "m1", "data": {"message": "x"}}),
    ("/api/agent/batch", {"agentId": "a1", "machine": "m1", "items": []}),
]

LEGACY_INGEST_ROUTES = [
    ("/api/ingest/start", {"strategy": "s", "machine": "m1"}),
    ("/api/ingest/heartbeat", {"strategy": "s", "machine": "m1"}),
    ("/api/ingest/trade", {"strategy": "s", "machine": "m1", "symbol": "X",
                           "direction": "long", "entry": 1.0, "quantity": 1.0}),
    ("/api/ingest/position", {"strategy": "s", "machine": "m1", "symbol": "X",
                              "direction": "long", "quantity": 1.0, "entry": 1.0}),
    ("/api/ingest/metric", {"strategy": "s", "machine": "m1", "name": "n", "value": 1.0}),
    ("/api/ingest/event", {"strategy": "s", "machine": "m1", "message": "x"}),
    ("/api/ingest/error", {"strategy": "s", "machine": "m1", "message": "x"}),
]

ALL_WRITE_ROUTES = AGENT_ROUTES + LEGACY_INGEST_ROUTES


# --------------------------------------------------------------------------- #
# Fail-closed
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("path,payload", ALL_WRITE_ROUTES)
def test_missing_token_is_rejected(client: TestClient, path: str, payload: dict) -> None:
    assert client.post(path, json=payload).status_code == 401


@pytest.mark.parametrize("path,payload", ALL_WRITE_ROUTES)
def test_wrong_token_is_rejected(client: TestClient, path: str, payload: dict) -> None:
    response = client.post(path, json=payload, headers=agent_headers("not-the-token"))
    assert response.status_code == 401


@pytest.mark.parametrize("path,payload", ALL_WRITE_ROUTES)
def test_unconfigured_server_rejects_everything(
    anon_client: TestClient, path: str, payload: dict
) -> None:
    """With no credential configured the endpoint is closed, not open.

    This is the specific behaviour that differs from
    ``raj_monitor/security.py::tokens_match``, which returns True when no token
    is set. That is safe on localhost and unsafe across a network.
    """
    assert anon_client.post(path, json=payload).status_code == 401
    assert anon_client.post(path, json=payload, headers=agent_headers()).status_code == 401


@pytest.mark.parametrize("path,payload", ALL_WRITE_ROUTES)
def test_valid_token_is_accepted(client: TestClient, path: str, payload: dict) -> None:
    response = client.post(path, json=payload, headers=agent_headers())
    assert response.status_code != 401, response.text
    assert response.status_code < 500, response.text


def test_empty_string_token_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/agent/heartbeat",
        json={"agentId": "a1", "machine": "m1"},
        headers={"X-Raj-Agent-Token": "   "},
    )
    assert response.status_code == 401


# --------------------------------------------------------------------------- #
# Machine scoping
# --------------------------------------------------------------------------- #
def test_scoped_token_accepts_its_own_machine(client: TestClient) -> None:
    response = client.post(
        "/api/agent/heartbeat",
        json={"agentId": "a1", "machine": SCOPED_MACHINE},
        headers=agent_headers(SCOPED_TOKEN),
    )
    assert response.status_code == 200, response.text


def test_scoped_token_rejects_another_machine(client: TestClient) -> None:
    """A leaked machine token must not be able to forge another host's telemetry."""
    response = client.post(
        "/api/agent/heartbeat",
        json={"agentId": "a1", "machine": "some-other-host"},
        headers=agent_headers(SCOPED_TOKEN),
    )
    assert response.status_code == 403


def test_fleet_token_accepts_any_machine(client: TestClient) -> None:
    response = client.post(
        "/api/agent/heartbeat",
        json={"agentId": "a1", "machine": "any-host-at-all"},
        headers=agent_headers(FLEET_TOKEN),
    )
    assert response.status_code == 200, response.text


def test_principal_scope_logic() -> None:
    fleet = AgentPrincipal(machine=None, agent_id="a")
    scoped = AgentPrincipal(machine="gcp-trading-01", agent_id="a")
    assert fleet.authorizes_machine("anything")
    assert fleet.authorizes_machine(None)
    assert scoped.authorizes_machine("gcp-trading-01")
    assert scoped.authorizes_machine("GCP-Trading-01")  # case-insensitive
    assert not scoped.authorizes_machine("other")
    # A machine-scoped credential must not write unattributed telemetry.
    assert not scoped.authorizes_machine(None)
    assert not scoped.authorizes_machine("")


# --------------------------------------------------------------------------- #
# Secret hygiene
# --------------------------------------------------------------------------- #
def test_token_never_appears_in_response_body(client: TestClient) -> None:
    for path, payload in ALL_WRITE_ROUTES:
        for headers in ({}, agent_headers(), agent_headers(SCOPED_TOKEN)):
            response = client.post(path, json=payload, headers=headers)
            body = response.text
            assert FLEET_TOKEN not in body
            assert SCOPED_TOKEN not in body
            assert DASHBOARD_TOKEN not in body


def test_token_never_appears_in_logs(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        client.post("/api/agent/heartbeat", json={"agentId": "a1", "machine": "m1"},
                    headers=agent_headers())
        client.post("/api/agent/heartbeat", json={"agentId": "a1", "machine": "m1"},
                    headers=agent_headers("a-wrong-token-value"))
        client.post("/api/agent/batch",
                    json={"agentId": "a1", "machine": "m1",
                          "items": [{"id": "e1", "kind": "nonsense-kind"}]},
                    headers=agent_headers())
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert FLEET_TOKEN not in logged
    assert SCOPED_TOKEN not in logged
    assert "a-wrong-token-value" not in logged


def test_rejection_reason_is_not_disclosed(client: TestClient) -> None:
    """Missing and invalid credentials must be indistinguishable to the caller.

    A different message for each would let an unauthenticated prober learn
    whether a guessed token exists at all.
    """
    missing = client.post("/api/agent/heartbeat", json={"agentId": "a", "machine": "m"})
    invalid = client.post("/api/agent/heartbeat", json={"agentId": "a", "machine": "m"},
                          headers=agent_headers("wrong"))
    assert missing.status_code == invalid.status_code == 401
    assert missing.json() == invalid.json()


# --------------------------------------------------------------------------- #
# Comparison primitives
# --------------------------------------------------------------------------- #
def test_constant_time_comparison_is_used() -> None:
    """`token_matches` compares fixed-width digests, never raw secrets."""
    digest = hash_token(FLEET_TOKEN)
    assert token_matches(FLEET_TOKEN, digest)
    assert not token_matches(FLEET_TOKEN + "x", digest)
    # A near-miss sharing a long prefix must not be accepted.
    assert not token_matches(FLEET_TOKEN[:-1] + "Z", digest)
    assert constant_time_equals(digest, digest)
    assert not constant_time_equals(digest, hash_token("other"))
    # Digests are fixed width regardless of input length, which is what removes
    # the timing signal from the comparison.
    assert len(hash_token("a")) == len(hash_token("a" * 5000)) == 64


def test_token_index_stores_only_digests(configure_env: None) -> None:
    from app.core.config import get_settings

    index = get_settings().agent_token_index
    assert index, "fixture should configure credentials"
    for key in index:
        assert len(key) == 64 and all(c in "0123456789abcdef" for c in key)
    assert FLEET_TOKEN not in index
    assert index[hash_token(FLEET_TOKEN)] is None            # fleet-wide
    assert index[hash_token(SCOPED_TOKEN)] == SCOPED_MACHINE  # machine-scoped


def test_multi_machine_scoped_tokens_authorization(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings
    from main import app

    google_token = "test-google-token-do-not-use-in-prod"
    mac_token = "test-mac-token-do-not-use-in-prod"
    google_machine = "google-vm-raj-quant-server"
    mac_machine = "index-option-local-mac"
    mac_agent = "index-option-local-mac-data-agent"

    monkeypatch.delenv("RAJ_AGENT_TOKEN", raising=False)
    monkeypatch.setenv(
        "RAJ_AGENT_TOKENS",
        f"{google_machine}:{google_token},{mac_machine}:{mac_token}",
    )
    get_settings.cache_clear()

    with TestClient(app) as test_client:
        # 1. Mac with Mac token -> 200
        res = test_client.post(
            "/api/agent/batch",
            json={"agentId": mac_agent, "machine": mac_machine, "items": []},
            headers={"X-Raj-Agent-Token": mac_token, "X-Raj-Agent-Id": mac_agent},
        )
        assert res.status_code == 200, res.text
        assert res.json()["accepted"] is True
        assert res.json()["machineId"] == f"mch-agent-{mac_machine}"

        # 2. Google with Google token -> 200
        res_g = test_client.post(
            "/api/agent/batch",
            json={"agentId": "google-vm-data-agent", "machine": google_machine, "items": []},
            headers={"X-Raj-Agent-Token": google_token, "X-Raj-Agent-Id": "google-vm-data-agent"},
        )
        assert res_g.status_code == 200, res_g.text
        assert res_g.json()["machineId"] == f"mch-agent-{google_machine}"

        # 3. Mac with Google token -> 403 Forbidden
        res_cross1 = test_client.post(
            "/api/agent/batch",
            json={"agentId": mac_agent, "machine": mac_machine, "items": []},
            headers={"X-Raj-Agent-Token": google_token, "X-Raj-Agent-Id": mac_agent},
        )
        assert res_cross1.status_code == 403

        # 4. Google with Mac token -> 403 Forbidden
        res_cross2 = test_client.post(
            "/api/agent/batch",
            json={"agentId": "google-vm-data-agent", "machine": google_machine, "items": []},
            headers={"X-Raj-Agent-Token": mac_token, "X-Raj-Agent-Id": "google-vm-data-agent"},
        )
        assert res_cross2.status_code == 403

        # 5. Mac with no token -> 401 Unauthorized
        res_unauthed = test_client.post(
            "/api/agent/batch",
            json={"agentId": mac_agent, "machine": mac_machine, "items": []},
        )
        assert res_unauthed.status_code == 401

