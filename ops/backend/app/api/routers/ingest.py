"""Ingestion router — endpoints the future ``monitor_sdk`` posts against.

These are the ONLY backend pieces the three trading projects need once the SDK
is written. Each endpoint maps 1:1 to a method on ``monitor``:

    monitor.start()     -> POST /api/ingest/start
    monitor.heartbeat() -> POST /api/ingest/heartbeat
    monitor.trade()     -> POST /api/ingest/trade
    monitor.position()  -> POST /api/ingest/position
    monitor.metric()    -> POST /api/ingest/metric
    monitor.event()     -> POST /api/ingest/event
    monitor.error()     -> POST /api/ingest/error

Status: **retained and secured, deprecated in favour of /api/agent/***.

The shipped agent does not use these routes — ``raj_monitor/constants.py`` maps
every kind to an ``/api/agent/*`` path, and the SDK reaches the backend only
through the Local Agent. They are kept because no evidence was found that
nothing else calls them, and removing a possibly-live endpoint is a bigger risk
than keeping a secured one. They carry the same authentication as the agent tier
and are marked deprecated in the OpenAPI schema.

Unlike ``/api/agent/*`` these routes do not persist to the telemetry tables
(they predate that work and write only to the events/logs feeds), which is a
further reason to prefer the agent tier.
"""

from fastapi import APIRouter, Depends

from app.api.dependencies.agent_auth import (
    AgentPrincipal,
    enforce_machine_scope,
    require_agent_token,
)
from app.schemas.ingest import (
    ErrorPayload,
    EventPayload,
    HeartbeatPayload,
    IngestAck,
    MetricPayload,
    PositionPayload,
    StartPayload,
    TradePayload,
)
from app.services import ingest_service

router = APIRouter(
    tags=["ingest"],
    dependencies=[Depends(require_agent_token)],
    deprecated=True,
)


@router.post("/start", response_model=IngestAck, summary="monitor.start()")
async def ingest_start(
    payload: StartPayload,
    principal: AgentPrincipal = Depends(require_agent_token),
) -> IngestAck:
    enforce_machine_scope(principal, payload.machine)
    return await ingest_service.handle_start(payload)


@router.post("/heartbeat", response_model=IngestAck, summary="monitor.heartbeat()")
async def ingest_heartbeat(
    payload: HeartbeatPayload,
    principal: AgentPrincipal = Depends(require_agent_token),
) -> IngestAck:
    enforce_machine_scope(principal, payload.machine)
    return await ingest_service.handle_heartbeat(payload)


@router.post("/trade", response_model=IngestAck, summary="monitor.trade()")
async def ingest_trade(
    payload: TradePayload,
    principal: AgentPrincipal = Depends(require_agent_token),
) -> IngestAck:
    enforce_machine_scope(principal, payload.machine)
    return await ingest_service.handle_trade(payload)


@router.post("/position", response_model=IngestAck, summary="monitor.position()")
async def ingest_position(
    payload: PositionPayload,
    principal: AgentPrincipal = Depends(require_agent_token),
) -> IngestAck:
    enforce_machine_scope(principal, payload.machine)
    return await ingest_service.handle_position(payload)


@router.post("/metric", response_model=IngestAck, summary="monitor.metric()")
async def ingest_metric(
    payload: MetricPayload,
    principal: AgentPrincipal = Depends(require_agent_token),
) -> IngestAck:
    enforce_machine_scope(principal, payload.machine)
    return await ingest_service.handle_metric(payload)


@router.post("/event", response_model=IngestAck, summary="monitor.event()")
async def ingest_event(
    payload: EventPayload,
    principal: AgentPrincipal = Depends(require_agent_token),
) -> IngestAck:
    enforce_machine_scope(principal, payload.machine)
    return await ingest_service.handle_event(payload)


@router.post("/error", response_model=IngestAck, summary="monitor.error()")
async def ingest_error(
    payload: ErrorPayload,
    principal: AgentPrincipal = Depends(require_agent_token),
) -> IngestAck:
    enforce_machine_scope(principal, payload.machine)
    return await ingest_service.handle_error(payload)
