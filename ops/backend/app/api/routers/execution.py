"""Execution router."""

from fastapi import APIRouter

from app.core.mock_policy import allow_mock_fixtures, empty_execution
from app.repositories import execution_doc
from app.schemas.execution import ExecutionData

router = APIRouter(tags=["execution"])


@router.get("/overview", response_model=ExecutionData, summary="Execution overview")
def get_execution() -> dict:
    if not allow_mock_fixtures():
        return empty_execution()
    return execution_doc
