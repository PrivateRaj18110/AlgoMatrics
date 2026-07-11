"""Alerts router."""

from fastapi import APIRouter

from app.repositories import alerts_repo
from app.schemas.alert import Alert

router = APIRouter(tags=["alerts"])


@router.get("", response_model=list[Alert], summary="List alerts")
def list_alerts() -> list[dict]:
    return alerts_repo.list()
