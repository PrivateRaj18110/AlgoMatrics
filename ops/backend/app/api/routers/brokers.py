"""Brokers router."""

from fastapi import APIRouter, HTTPException

from app.repositories import brokers_repo
from app.schemas.broker import Broker
from app.services import algomatrics_service

router = APIRouter(tags=["brokers"])


@router.get("", response_model=list[Broker], summary="List brokers")
def list_brokers() -> list[dict]:
    live = algomatrics_service.brokers()
    return live if live is not None else brokers_repo.list()


@router.get("/{broker_id}", response_model=Broker, summary="Get a broker")
def get_broker(broker_id: str) -> dict:
    if algomatrics_service.brokers() is not None:
        broker = algomatrics_service.broker(broker_id)
    else:
        broker = brokers_repo.get(broker_id)
    if broker is None:
        raise HTTPException(status_code=404, detail="Broker not found")
    return broker
