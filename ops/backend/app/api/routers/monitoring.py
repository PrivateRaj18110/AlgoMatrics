"""monitoring.v1 — canonical ingress and read API.

The ingress accepts exactly one thing: a single monitoring.v1 message, validated
against the producer's published schema. There is no batch wrapper, because
monitoring.v1 does not define one, and no ``data: dict`` escape hatch, because a
route that accepts anything eventually receives everything.

The read API is observational. No endpoint here cancels, modifies, resubmits,
flattens, restarts, halts or executes anything — not disabled, not
permission-gated, not present. A structural test asserts that against the
published OpenAPI surface so it stays true.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy import select

from app.api.dependencies.dashboard_auth import require_dashboard_viewer
from app.api.dependencies.monitoring_auth import (
    MonitoringAdmin,
    MonitoringPrincipal,
    require_monitoring_admin,
    require_monitoring_publisher,
)
from app.core.config import get_settings
from app.database.session import database_enabled, get_sessionmaker
from app.models.monitoring import (
    UNKNOWN_DEPLOYMENT,
    MonitoringEvidence,
    MonitoringProjection,
    MonitoringQuarantine,
    MonitoringSequenceState,
)
from app.monitoring import contract, receiver, views

router = APIRouter(tags=["monitoring.v1"])


def _deployment() -> str:
    configured = (get_settings().monitoring_deployment_environment or "").strip()
    return configured or UNKNOWN_DEPLOYMENT


# --------------------------------------------------------------------------- #
# Canonical ingress
# --------------------------------------------------------------------------- #
@router.post(
    "/messages",
    summary="Receive one monitoring.v1 message from the LLS Monitoring Backend",
    status_code=status.HTTP_200_OK,
)
async def receive_message(
    request: Request,
    response: Response,
    principal: MonitoringPrincipal = Depends(require_monitoring_publisher),
    x_monitoring_sha256: str | None = Header(default=None, alias="X-Monitoring-SHA256"),
    content_encoding: str | None = Header(default=None, alias="Content-Encoding"),
) -> dict:
    """Validate, store and project one message, then acknowledge it.

    Returns the exact ``monitoring.ack.v1`` body. The producer validates every
    field of it and treats any mismatch as a failed delivery, so nothing extra is
    added to the response.

    The acknowledgement is produced only after evidence is committed: the
    producer deletes from its durable queue on success, so acknowledging before
    the write was durable would lose data on a crash between the two.
    """
    # Read after authentication, never before — a body must not be parsed on
    # behalf of a caller whose credential has not been established.
    raw_body = await request.body()

    try:
        ack = receiver.ingest_message(
            raw_body,
            principal,
            declared_digest=x_monitoring_sha256,
            content_encoding=content_encoding,
        )
    except receiver.StorageUnavailable as exc:
        # The producer must keep its queue and retry — never a 200.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except contract.ContractUnavailable as exc:
        # Cannot validate means cannot accept. Transient from the producer's
        # point of view: fix the deployment, the queued data is still good.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except receiver.ReceiverRefusal as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "reason": exc.reason,
                "detail": exc.detail,
                "quarantine_id": exc.quarantine_id,
            },
        ) from exc

    response.status_code = status.HTTP_200_OK
    return ack.as_dict()


# --------------------------------------------------------------------------- #
# Read API
# --------------------------------------------------------------------------- #
def _session():
    if not database_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="monitoring.v1 storage is not configured on this deployment",
        )
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


@router.get("/state", summary="Current monitoring state")
def current_state(
    _viewer=Depends(require_dashboard_viewer),
    session=Depends(_session),
    message_type: str | None = Query(default=None),
    source_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict:
    """Current projections, each carrying the producer's own qualifiers.

    Scoped to this receiver's configured deployment tier. That scoping is a
    storage boundary applied in the query, not a display filter: a staging
    observation is never loaded into a production response.
    """
    deployment = _deployment()
    query = select(MonitoringProjection).where(
        MonitoringProjection.receiver_deployment_environment == deployment
    )
    if message_type:
        query = query.where(MonitoringProjection.message_type == message_type)
    if source_id:
        query = query.where(MonitoringProjection.source_id == source_id)
    query = query.order_by(
        MonitoringProjection.message_type, MonitoringProjection.capture_ref
    ).limit(limit)

    rows = [views.projection_view(row) for row in session.execute(query).scalars()]
    return {
        "receiverDeploymentEnvironment": deployment,
        "count": len(rows),
        "items": rows,
    }


@router.get("/evidence/{message_id:path}", summary="One received message, as stored")
def evidence(
    message_id: str,
    _viewer=Depends(require_dashboard_viewer),
    session=Depends(_session),
) -> dict:
    row = session.get(MonitoringEvidence, message_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="no such message")
    return views.evidence_view(row)


@router.get("/history", summary="Evidence history, oldest first")
def history(
    _viewer=Depends(require_dashboard_viewer),
    session=Depends(_session),
    message_type: str | None = Query(default=None),
    source_instance: str | None = Query(default=None),
    capture_ref: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    """Every accepted message, oldest first.

    Superseded observations are still here: a projection moving forward never
    removes the evidence it moved on from, so an outage between two readings
    stays visible rather than being smoothed over.
    """
    query = select(MonitoringEvidence).where(
        MonitoringEvidence.receiver_deployment_environment == _deployment()
    )
    if message_type:
        query = query.where(MonitoringEvidence.message_type == message_type)
    if source_instance:
        query = query.where(MonitoringEvidence.source_instance == source_instance)
    if capture_ref:
        query = query.where(MonitoringEvidence.capture_ref == capture_ref)
    query = query.order_by(
        MonitoringEvidence.generated_at, MonitoringEvidence.sequence_ordinal
    ).limit(limit)
    rows = [views.evidence_view(row) for row in session.execute(query).scalars()]
    return {"count": len(rows), "items": rows}


@router.get("/sources", summary="Ordered-acceptance state per publisher instance")
def sources(
    _viewer=Depends(require_dashboard_viewer),
    session=Depends(_session),
) -> dict:
    query = select(MonitoringSequenceState).order_by(
        MonitoringSequenceState.source_id, MonitoringSequenceState.source_instance
    )
    rows = [views.sequence_view(row) for row in session.execute(query).scalars()]
    return {"count": len(rows), "items": rows}


@router.get("/health", summary="Receiver health — not LLS health")
def health(session=Depends(_session)) -> dict:
    """The health of **this** receiver.

    Deliberately says nothing about LLS. A healthy ingress means messages can be
    received; whether the trading system is well is a question only the
    Monitoring Backend answers, and it answers it in its own payloads.
    """
    quarantined = session.execute(select(MonitoringQuarantine.quarantine_id).limit(1000)).all()
    return {
        "receiver": "monitoring.v1",
        "contractAvailable": contract.contract_available(),
        "supportedSchemaVersion": contract.MONITORING_SCHEMA_VERSION,
        "ackSchemaVersion": receiver.ACK_SCHEMA_VERSION,
        "storageConfigured": database_enabled(),
        "receiverDeploymentEnvironment": _deployment(),
        "quarantinedMessages": len(quarantined),
        # Stated explicitly so no caller mistakes this for a verdict on LLS.
        "llsHealth": "NOT_DETERMINED_HERE",
    }


# --------------------------------------------------------------------------- #
# Administration
# --------------------------------------------------------------------------- #
@router.get("/quarantine", summary="Quarantined material (administrators only)")
def quarantine(
    _admin: MonitoringAdmin = Depends(require_monitoring_admin),
    session=Depends(_session),
    limit: int = Query(default=100, ge=1, le=500),
    reason: str | None = Query(default=None),
) -> dict:
    """Messages that never entered a projection, and why.

    Not visible to dashboard viewers: quarantined material is data the receiver
    could not accept, and presenting it beside validated monitoring data would
    give it a credibility it has not earned.
    """
    query = select(MonitoringQuarantine).order_by(MonitoringQuarantine.received_at.desc())
    if reason:
        query = query.where(MonitoringQuarantine.reason == reason)
    rows = [views.quarantine_view(row) for row in session.execute(query.limit(limit)).scalars()]
    return {"count": len(rows), "items": rows}
