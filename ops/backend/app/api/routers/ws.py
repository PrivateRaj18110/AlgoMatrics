"""Websocket router.

Clients connect to ``/api/ws`` and receive the same typed message protocol the
frontend mock engine emits. On connect we send an initial machine snapshot, then
the background publisher streams telemetry, events and heartbeats.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.realtime.broadcaster import broadcaster
from app.repositories import machines_repo

router = APIRouter()


@router.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await broadcaster.connect(websocket)
    try:
        # Prime the client with the current machine snapshot.
        await websocket.send_json({"type": "machines", "payload": machines_repo.list()})
        while True:
            # We don't expect inbound messages, but keep the socket draining so
            # disconnects are detected promptly.
            await websocket.receive_text()
    except WebSocketDisconnect:
        await broadcaster.disconnect(websocket)
    except Exception:
        await broadcaster.disconnect(websocket)
