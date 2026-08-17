"""Alerts router."""

from fastapi import APIRouter

from app.core.mock_policy import allow_mock_fixtures
from app.repositories import alerts_repo
from app.schemas.alert import Alert

router = APIRouter(tags=["alerts"])


@router.get("", response_model=list[Alert], summary="List alerts")
def list_alerts() -> list[dict]:
    if not allow_mock_fixtures():
        return []
    return alerts_repo.list()
