"""Websocket connection manager + broadcaster.

The broadcaster fans messages out to every connected client. Messages use the
same typed protocol the frontend's mock engine emits:

    {"type": "machines", "payload": [...]}
    {"type": "event", "payload": {...}}
    {"type": "connection", "payload": {"latencyMs": 8, "time": "..."}}
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket


class Broadcaster:
    """Tracks active websocket clients and pushes JSON messages to them."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send a message to every client, dropping any that have gone away."""
        async with self._lock:
            targets = list(self._clients)
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)


broadcaster = Broadcaster()
