from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from algo_platform.api.websocket.hub import (
    inbound_payload_too_large,
    router,
    websocket_origin_allowed,
)


def test_websocket_origin_allowed_when_header_absent() -> None:
    assert websocket_origin_allowed(None, ["https://algomatrics.in"]) is True


def test_websocket_origin_allowed_matches_allowlist() -> None:
    allowed = ["https://algomatrics.in", "http://localhost:5173"]
    assert websocket_origin_allowed("https://algomatrics.in", allowed) is True
    assert websocket_origin_allowed("https://malicious-example.com", allowed) is False


def test_inbound_payload_over_8kb_is_rejected() -> None:
    assert inbound_payload_too_large("x" * 8192) is False
    assert inbound_payload_too_large("x" * 8193) is True


def _ws_app(*, ticket_payload: dict[str, object] | None) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    redis = AsyncMock()
    redis.get_json = AsyncMock(return_value=ticket_payload)
    redis.delete = AsyncMock()
    redis.subscribe_json = AsyncMock()
    app.state.redis = redis
    app.state.settings = SimpleNamespace(cors_origins=["https://algomatrics.in"])
    app.state.prometheus = None
    return app


def test_websocket_rejects_disallowed_origin() -> None:
    app = _ws_app(ticket_payload={"organization_id": str(uuid4()), "user_id": str(uuid4())})
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as raised:
        with client.websocket_connect(
            "/api/v1/ws?ticket=abcdefghijklmnop",
            headers={"Origin": "https://malicious-example.com"},
        ):
            pass
    assert raised.value.code == 4403


def test_websocket_accepts_allowlisted_origin_then_requires_ticket() -> None:
    app = _ws_app(ticket_payload=None)
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as raised:
        with client.websocket_connect(
            "/api/v1/ws?ticket=abcdefghijklmnop",
            headers={"Origin": "https://algomatrics.in"},
        ):
            pass
    assert raised.value.code == 4401


def test_websocket_missing_origin_is_allowed_for_non_browser_clients() -> None:
    app = _ws_app(ticket_payload=None)
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as raised:
        with client.websocket_connect("/api/v1/ws?ticket=abcdefghijklmnop"):
            pass
    assert raised.value.code == 4401


def test_websocket_closes_on_oversized_message() -> None:
    payload = {"organization_id": str(uuid4()), "user_id": str(uuid4())}
    app = _ws_app(ticket_payload=payload)
    client = TestClient(app)
    with client.websocket_connect(
        "/api/v1/ws?ticket=abcdefghijklmnop",
        headers={"Origin": "https://algomatrics.in"},
    ) as ws:
        with pytest.raises(WebSocketDisconnect) as raised:
            ws.send_text("x" * 9000)
            ws.receive_text()
    assert raised.value.code == 1009


def test_websocket_malformed_json_returns_error_without_disconnect() -> None:
    payload = {"organization_id": str(uuid4()), "user_id": str(uuid4())}
    app = _ws_app(ticket_payload=payload)
    client = TestClient(app)
    with client.websocket_connect(
        "/api/v1/ws?ticket=abcdefghijklmnop",
        headers={"Origin": "https://algomatrics.in"},
    ) as ws:
        ws.send_text("not-json{")
        message = ws.receive_json()
        assert message["type"] == "error"
        assert message["detail"] == "invalid JSON"
