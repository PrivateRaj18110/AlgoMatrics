"""Authenticated WebSocket fan-out.

Clients obtain a short-lived single-use ticket via ``POST /auth/ws-ticket``,
connect to ``/api/v1/ws?ticket=...``, then subscribe to channels. Server-side
state stays in Redis pub/sub; each connection has a bounded send queue and a
heartbeat, and slow consumers are disconnected rather than buffered forever.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from algo_platform.shared.infrastructure.redis_gateway import RedisGateway
from algo_platform.shared.infrastructure.security import hash_token

logger = structlog.get_logger(__name__)

router = APIRouter()

_ALLOWED_STATIC_CHANNELS = {
    "orders",
    "positions",
    "portfolio",
    "notifications",
    "strategy-runs",
    "risk",
}
_MAX_SUBSCRIPTIONS = 30
_SEND_QUEUE_SIZE = 200
_HEARTBEAT_SECONDS = 20.0


def _redis_channel(channel: str, organization_id: UUID) -> str | None:
    if channel in _ALLOWED_STATIC_CHANNELS:
        return f"{channel}:{organization_id}"
    if channel.startswith("ticks:"):
        instrument = channel.split(":", 1)[1]
        try:
            UUID(instrument)
        except ValueError:
            return None
        return f"ticks:{instrument}"
    return None


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket, ticket: str = Query(min_length=10, max_length=200)
) -> None:
    redis: RedisGateway = websocket.app.state.redis
    ticket_key = f"ws:ticket:{hash_token(ticket)}"
    payload = await redis.get_json(ticket_key)
    if payload is None:
        await websocket.close(code=4401, reason="invalid or expired ticket")
        return
    await redis.delete(ticket_key)  # single use
    try:
        organization_id = UUID(str(payload["organization_id"]))
        user_id = str(payload["user_id"])
    except (KeyError, ValueError):
        await websocket.close(code=4401, reason="malformed ticket")
        return

    await websocket.accept()
    send_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=_SEND_QUEUE_SIZE)
    subscriptions: dict[str, str] = {}
    pump_task: asyncio.Task[None] | None = None
    sequence = 0

    async def pump_redis() -> None:
        channels = list(subscriptions.values())
        if not channels:
            return
        async for _channel, message in redis.subscribe_json(*channels):
            try:
                send_queue.put_nowait(message)
            except asyncio.QueueFull:
                logger.warning("ws.slow_consumer_disconnect", user_id=user_id)
                await websocket.close(code=4408, reason="slow consumer")
                return

    async def restart_pump() -> None:
        nonlocal pump_task
        if pump_task is not None:
            pump_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pump_task
        pump_task = asyncio.create_task(pump_redis()) if subscriptions else None

    async def sender() -> None:
        nonlocal sequence
        while True:
            try:
                message = await asyncio.wait_for(send_queue.get(), timeout=_HEARTBEAT_SECONDS)
            except TimeoutError:
                await websocket.send_text(json.dumps({"type": "heartbeat"}))
                continue
            sequence += 1
            message.setdefault("type", "event")
            message["seq"] = sequence
            await websocket.send_text(json.dumps(message, default=str))

    sender_task = asyncio.create_task(sender())
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                command = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"type": "error", "detail": "invalid JSON"}))
                continue
            action = command.get("action")
            channels = command.get("channels", [])
            if action == "subscribe" and isinstance(channels, list):
                for channel in channels[:_MAX_SUBSCRIPTIONS]:
                    resolved = _redis_channel(str(channel), organization_id)
                    if resolved is None:
                        await websocket.send_text(
                            json.dumps({"type": "error", "detail": f"unknown channel {channel}"})
                        )
                        continue
                    if len(subscriptions) >= _MAX_SUBSCRIPTIONS:
                        break
                    subscriptions[str(channel)] = resolved
                await restart_pump()
                await websocket.send_text(
                    json.dumps({"type": "subscribed", "channels": sorted(subscriptions)})
                )
            elif action == "unsubscribe" and isinstance(channels, list):
                for channel in channels:
                    subscriptions.pop(str(channel), None)
                await restart_pump()
                await websocket.send_text(
                    json.dumps({"type": "subscribed", "channels": sorted(subscriptions)})
                )
            elif action == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    finally:
        sender_task.cancel()
        if pump_task is not None:
            pump_task.cancel()
        for task in (sender_task, pump_task):
            if task is not None:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
