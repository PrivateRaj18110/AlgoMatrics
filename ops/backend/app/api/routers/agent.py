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

**Authentication.** Every route requires a valid ``X-Raj-Agent-Token``
(``require_agent_token``, applied at router level so a new route cannot be added
unauthenticated by accident). A machine-scoped credential may only write
telemetry for its own machine — enforced per-request against the payload body.

**Failure semantics.** A batch containing a transient failure returns 503 rather
than 200, so the agent's durable queue holds the envelopes and retries. Returning
200 would make the agent delete data the server never stored. Permanent
rejections stay in the 200 response as per-item outcomes: retrying them can never
succeed, and they are recorded in the dead-letter table instead.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies.agent_auth import (
    AgentPrincipal,
    enforce_machine_scope,
    require_agent_token,
)
from app.core.config import get_settings
from app.schemas.agent import (
    AgentAck,
    AgentBatch,
    AgentHeartbeat,
    AgentRegister,
    Envelope,
)
from app.services import agent_service

router = APIRouter(tags=["agent"], dependencies=[Depends(require_agent_token)])


def _guard_transient(ack: AgentAck) -> AgentAck:
    """Turn a transient-failure ack into a 503 so the agent retries."""
    if ack.failed:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="telemetry store unavailable; retry with the queued batch",
        )
    return ack


@router.post("/register", response_model=AgentAck, summary="Agent register")
async def agent_register(
    payload: AgentRegister,
    principal: AgentPrincipal = Depends(require_agent_token),
) -> AgentAck:
    enforce_machine_scope(principal, payload.machine)
    return await agent_service.handle_register(payload)


@router.post("/heartbeat", response_model=AgentAck, summary="Agent heartbeat")
async def agent_heartbeat(
    payload: AgentHeartbeat,
    principal: AgentPrincipal = Depends(require_agent_token),
) -> AgentAck:
    enforce_machine_scope(principal, payload.machine)
    return await agent_service.handle_heartbeat(payload)


@router.post("/metrics", response_model=AgentAck, summary="Agent metrics")
async def agent_metrics(
    payload: Envelope,
    principal: AgentPrincipal = Depends(require_agent_token),
) -> AgentAck:
    enforce_machine_scope(principal, payload.machine)
    return _guard_transient(
        await agent_service.handle_metrics_endpoint(payload, principal.agent_id)
    )


@router.post("/events", response_model=AgentAck, summary="Agent events")
async def agent_events(
    payload: Envelope,
    principal: AgentPrincipal = Depends(require_agent_token),
) -> AgentAck:
    enforce_machine_scope(principal, payload.machine)
    return _guard_transient(await agent_service.handle_events(payload, principal.agent_id))


@router.post("/trades", response_model=AgentAck, summary="Agent trades")
async def agent_trades(
    payload: Envelope,
    principal: AgentPrincipal = Depends(require_agent_token),
) -> AgentAck:
    enforce_machine_scope(principal, payload.machine)
    return _guard_transient(
        await agent_service.handle_trades_endpoint(payload, principal.agent_id)
    )


@router.post("/logs", response_model=AgentAck, summary="Agent logs")
async def agent_logs(
    payload: Envelope,
    principal: AgentPrincipal = Depends(require_agent_token),
) -> AgentAck:
    enforce_machine_scope(principal, payload.machine)
    return _guard_transient(
        await agent_service.handle_logs_endpoint(payload, principal.agent_id)
    )


@router.post("/batch", response_model=AgentAck, summary="Agent batch upload")
async def agent_batch(
    payload: AgentBatch,
    principal: AgentPrincipal = Depends(require_agent_token),
) -> AgentAck:
    enforce_machine_scope(principal, payload.machine)
    limit = get_settings().ingest_max_batch_items
    if len(payload.items) > limit:
        # Bound the work one request can demand. The agent's own batch size is
        # 200; this ceiling leaves generous replay headroom.
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"batch exceeds {limit} items",
        )
    return _guard_transient(await agent_service.handle_batch(payload, principal.agent_id))
