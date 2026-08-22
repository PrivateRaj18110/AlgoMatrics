"""Machines router."""

from fastapi import APIRouter, HTTPException

from app.repositories import machines_repo
from app.schemas.machine import Machine

router = APIRouter(tags=["machines"])


@router.get("", response_model=list[Machine], summary="List machines")
def list_machines() -> list[dict]:
    return machines_repo.list()


@router.get("/{machine_id}", response_model=Machine, summary="Get a machine")
def get_machine(machine_id: str) -> dict:
    machine = machines_repo.get(machine_id)
    if machine is None:
        raise HTTPException(status_code=404, detail="Machine not found")
    return machine
