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
"""

from fastapi import APIRouter

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

router = APIRouter(tags=["ingest"])


@router.post("/start", response_model=IngestAck, summary="monitor.start()")
async def ingest_start(payload: StartPayload) -> IngestAck:
    return await ingest_service.handle_start(payload)


@router.post("/heartbeat", response_model=IngestAck, summary="monitor.heartbeat()")
async def ingest_heartbeat(payload: HeartbeatPayload) -> IngestAck:
    return await ingest_service.handle_heartbeat(payload)


@router.post("/trade", response_model=IngestAck, summary="monitor.trade()")
async def ingest_trade(payload: TradePayload) -> IngestAck:
    return await ingest_service.handle_trade(payload)


@router.post("/position", response_model=IngestAck, summary="monitor.position()")
async def ingest_position(payload: PositionPayload) -> IngestAck:
    return await ingest_service.handle_position(payload)


@router.post("/metric", response_model=IngestAck, summary="monitor.metric()")
async def ingest_metric(payload: MetricPayload) -> IngestAck:
    return await ingest_service.handle_metric(payload)


@router.post("/event", response_model=IngestAck, summary="monitor.event()")
async def ingest_event(payload: EventPayload) -> IngestAck:
    return await ingest_service.handle_event(payload)


@router.post("/error", response_model=IngestAck, summary="monitor.error()")
async def ingest_error(payload: ErrorPayload) -> IngestAck:
    return await ingest_service.handle_error(payload)
