"""Accounts router."""

from fastapi import APIRouter, HTTPException

from app.repositories import accounts_repo
from app.schemas.account import Account
from app.services import algomatrics_service

router = APIRouter(tags=["accounts"])


@router.get("", response_model=list[Account], summary="List accounts")
def list_accounts() -> list[dict]:
    live = algomatrics_service.accounts()
    return live if live is not None else accounts_repo.list()


@router.get("/{account_id}", response_model=Account, summary="Get an account")
def get_account(account_id: str) -> dict:
    if algomatrics_service.accounts() is not None:
        account = algomatrics_service.account(account_id)
    else:
        account = accounts_repo.get(account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return account
