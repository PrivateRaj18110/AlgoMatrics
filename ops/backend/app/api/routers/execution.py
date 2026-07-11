"""Execution router."""

from fastapi import APIRouter

from app.repositories import execution_doc
from app.schemas.execution import ExecutionData

router = APIRouter(tags=["execution"])


@router.get("/overview", response_model=ExecutionData, summary="Execution overview")
def get_execution() -> dict:
    return execution_doc
