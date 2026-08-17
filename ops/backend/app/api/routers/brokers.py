"""Brokers router."""

from fastapi import APIRouter, HTTPException

from app.core.mock_policy import allow_mock_fixtures
from app.repositories import brokers_repo
from app.schemas.broker import Broker
from app.services import algomatrics_service
from app.services.telemetry_read_models import telemetry_brokers

router = APIRouter(tags=["brokers"])


@router.get("", response_model=list[Broker], summary="List brokers")
def list_brokers() -> list[dict]:
    if not allow_mock_fixtures():
        return telemetry_brokers()
    live = algomatrics_service.brokers()
    return live if live is not None else brokers_repo.list()


@router.get("/{broker_id}", response_model=Broker, summary="Get a broker")
def get_broker(broker_id: str) -> dict:
    if not allow_mock_fixtures():
        broker = next((row for row in telemetry_brokers() if row["id"] == broker_id), None)
    elif algomatrics_service.brokers() is not None:
        broker = algomatrics_service.broker(broker_id)
    else:
        broker = brokers_repo.get(broker_id)
    if broker is None:
        raise HTTPException(status_code=404, detail="Broker not found")
    return broker
