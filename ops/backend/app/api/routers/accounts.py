"""Accounts router."""

from fastapi import APIRouter, HTTPException

from app.core.mock_policy import allow_mock_fixtures
from app.repositories import accounts_repo
from app.schemas.account import Account
from app.services import algomatrics_service
from app.services.telemetry_read_models import telemetry_accounts

router = APIRouter(tags=["accounts"])


@router.get("", response_model=list[Account], summary="List accounts")
def list_accounts() -> list[dict]:
    if not allow_mock_fixtures():
        return telemetry_accounts()
    live = algomatrics_service.accounts()
    return live if live is not None else accounts_repo.list()


@router.get("/{account_id}", response_model=Account, summary="Get an account")
def get_account(account_id: str) -> dict:
    if not allow_mock_fixtures():
        account = next((row for row in telemetry_accounts() if row["id"] == account_id), None)
    elif algomatrics_service.accounts() is not None:
        account = algomatrics_service.account(account_id)
    else:
        account = accounts_repo.get(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return account
