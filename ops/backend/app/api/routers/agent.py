"""Agent router — endpoints the Raj Local Agent posts against.

    POST /api/agent/register    -> agent_service.handle_register
    POST /api/agent/heartbeat   -> agent_service.handle_heartbeat
    POST /api/agent/metrics     -> agent_service.handle_metrics_endpoint
    POST /api/agent/events      -> agent_service.handle_events
    POST /api/agent/trades      -> agent_service.handle_trades_endpoint
    POST /api/agent/logs        -> agent_service.handle_logs_endpoint
    POST /api/agent/batch       -> agent_service.handle_batch   (primary path)

The agent is the only client; strategies never call these directly. Gzip request
bodies (``Content-Encoding: gzip``) are transparently decompressed upstream by
``GzipRequestMiddleware``.
"""

from fastapi import APIRouter

from app.schemas.agent import (
    AgentAck,
    AgentBatch,
    AgentHeartbeat,
    AgentRegister,
    Envelope,
)
from app.services import agent_service

router = APIRouter(tags=["agent"])


@router.post("/register", response_model=AgentAck, summary="Agent register")
async def agent_register(payload: AgentRegister) -> AgentAck:
    return await agent_service.handle_register(payload)


@router.post("/heartbeat", response_model=AgentAck, summary="Agent heartbeat")
async def agent_heartbeat(payload: AgentHeartbeat) -> AgentAck:
    return await agent_service.handle_heartbeat(payload)


@router.post("/metrics", response_model=AgentAck, summary="Agent metrics")
async def agent_metrics(payload: Envelope) -> AgentAck:
    return await agent_service.handle_metrics_endpoint(payload)


@router.post("/events", response_model=AgentAck, summary="Agent events")
async def agent_events(payload: Envelope) -> AgentAck:
    return await agent_service.handle_events(payload)


@router.post("/trades", response_model=AgentAck, summary="Agent trades")
async def agent_trades(payload: Envelope) -> AgentAck:
    return await agent_service.handle_trades_endpoint(payload)


@router.post("/logs", response_model=AgentAck, summary="Agent logs")
async def agent_logs(payload: Envelope) -> AgentAck:
    return await agent_service.handle_logs_endpoint(payload)


@router.post("/batch", response_model=AgentAck, summary="Agent batch upload")
async def agent_batch(payload: AgentBatch) -> AgentAck:
    return await agent_service.handle_batch(payload)
