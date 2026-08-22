"""Websocket router.

Clients connect to ``/api/ws`` and receive the same typed message protocol the
frontend mock engine emits. On connect we send an initial machine snapshot, then
the background publisher streams telemetry, events and heartbeats.

**Authentication.** This socket carries live machine state, trades and events, so
it is no longer anonymous. The handshake is rejected *before* ``accept()``, which
means an unauthenticated client never receives a single frame — not even the
initial machine snapshot. Credentials travel in ``Sec-WebSocket-Protocol`` (see
``app/api/dependencies/dashboard_auth.py``) rather than the query string, so they
cannot leak into access logs.
"""

from fastapi import APIRouter, WebSocket, status

from app.api.dependencies.dashboard_auth import authenticate_viewer, extract_credential
from app.realtime.broadcaster import broadcaster
from app.repositories import machines_repo

router = APIRouter()


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    credential, subprotocol = extract_credential(
        websocket.headers.get("sec-websocket-protocol"),
        websocket.headers.get("authorization"),
    )
    viewer = authenticate_viewer(credential)
    if viewer is None:
        # Close during the handshake: no accept(), so no telemetry is emitted.
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # The negotiated subprotocol must be echoed or the browser fails the handshake.
    await broadcaster.connect(websocket, subprotocol=subprotocol)
    try:
        # Prime the client with the current machine snapshot.
        await websocket.send_json({"type": "machines", "payload": machines_repo.list()})
        while True:
            # We don't expect inbound messages, but keep the socket draining so
            # disconnects are detected promptly.
            await websocket.receive_text()
    except Exception:
        # Covers WebSocketDisconnect and any transport error alike.
        await broadcaster.disconnect(websocket)
