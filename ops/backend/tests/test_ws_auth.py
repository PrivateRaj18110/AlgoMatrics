"""Websocket authentication coverage.

``/api/ws`` streams live machine state, trades and events. It was previously
anonymous; these tests pin the rule that an unauthenticated client receives
*nothing* — the handshake is refused before ``accept()``, so not even the initial
machine snapshot is emitted.
"""

from __future__ import annotations

import pytest
from app.api.dependencies.dashboard_auth import (
    CREDENTIAL_SUBPROTOCOL,
    authenticate_viewer,
    extract_credential,
)
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.conftest import DASHBOARD_TOKEN, agent_headers


def _subprotocol(token: str) -> list[str]:
    return [CREDENTIAL_SUBPROTOCOL, token]


def test_unauthenticated_websocket_is_rejected(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/api/ws") as ws:
        ws.receive_json()


def test_invalid_credential_is_rejected(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect), client.websocket_connect(
        "/api/ws", subprotocols=_subprotocol("nope")
    ) as ws:
        ws.receive_json()


def test_authenticated_websocket_is_accepted(client: TestClient) -> None:
    with client.websocket_connect("/api/ws", subprotocols=_subprotocol(DASHBOARD_TOKEN)) as ws:
        initial = ws.receive_json()
    assert initial["type"] == "machines"


def test_authenticated_websocket_can_reconnect_and_receive_new_events(
    client: TestClient,
) -> None:
    with client.websocket_connect("/api/ws", subprotocols=_subprotocol(DASHBOARD_TOKEN)) as ws:
        assert ws.receive_json()["type"] == "machines"

    with client.websocket_connect("/api/ws", subprotocols=_subprotocol(DASHBOARD_TOKEN)) as ws:
        assert ws.receive_json()["type"] == "machines"
        response = client.post(
            "/api/agent/events",
            json={
                "id": "ws-reconnect-event",
                "kind": "event",
                "machine": "gcp-trading-01",
                "strategy": "phase3-ws",
                "data": {
                    "category": "system",
                    "severity": "info",
                    "message": "websocket reconnect regression",
                },
            },
            headers=agent_headers(),
        )
        assert response.status_code == 200, response.text
        notification = ws.receive_json()

    assert notification["type"] == "event"
    assert notification["payload"]["message"] == "websocket reconnect regression"


def test_authorization_header_is_accepted(client: TestClient) -> None:
    """Non-browser clients (tests, probes) may use a normal bearer header."""
    with client.websocket_connect(
        "/api/ws", headers={"Authorization": f"Bearer {DASHBOARD_TOKEN}"}
    ) as ws:
        assert ws.receive_json()["type"] == "machines"


def test_unconfigured_server_rejects_every_viewer(anon_client: TestClient) -> None:
    """Fail closed: no dashboard credential configured means no subscribers."""
    with pytest.raises(WebSocketDisconnect), anon_client.websocket_connect(
        "/api/ws", subprotocols=_subprotocol(DASHBOARD_TOKEN)
    ) as ws:
        ws.receive_json()


def test_no_telemetry_leaks_before_authentication(client: TestClient) -> None:
    """A rejected client must not receive a single frame."""
    received = []
    try:
        with client.websocket_connect("/api/ws") as ws:
            received.append(ws.receive_json())
    except WebSocketDisconnect:
        pass
    assert received == []


# --------------------------------------------------------------------------- #
# Credential extraction
# --------------------------------------------------------------------------- #
def test_extract_credential_from_subprotocol() -> None:
    credential, negotiated = extract_credential(f"{CREDENTIAL_SUBPROTOCOL}, abc123", None)
    assert credential == "abc123"
    # The negotiated protocol must be echoed back or browsers fail the handshake.
    assert negotiated == CREDENTIAL_SUBPROTOCOL


def test_extract_credential_from_authorization_header() -> None:
    credential, negotiated = extract_credential(None, "Bearer abc123")
    assert credential == "abc123"
    assert negotiated is None


def test_extract_credential_ignores_unrelated_subprotocol() -> None:
    assert extract_credential("graphql-ws", None) == (None, None)


def test_extract_credential_handles_absent_headers() -> None:
    assert extract_credential(None, None) == (None, None)


def test_authenticate_viewer_rejects_none_credential(configure_env: None) -> None:
    assert authenticate_viewer(None) is None
    assert authenticate_viewer("") is None


def test_viewer_subject_does_not_contain_the_credential(configure_env: None) -> None:
    viewer = authenticate_viewer(DASHBOARD_TOKEN)
    assert viewer is not None
    assert DASHBOARD_TOKEN not in viewer.subject
    assert viewer.kind == "token"
