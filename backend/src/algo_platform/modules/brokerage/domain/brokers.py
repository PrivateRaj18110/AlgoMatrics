"""Brokerage aggregates: venue catalog, encrypted connections, trading accounts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from algo_platform.shared.domain.errors import ConflictError, ValidationFailed
from algo_platform.shared.domain.types import AccountId, TenantId, UserId, utc_now


class BrokerCode(StrEnum):
    PAPER = "paper"
    MT5 = "mt5"
    ZERODHA = "zerodha"
    ANGELONE = "angelone"
    DELTA = "delta"
    BINANCE = "binance"
    INTERACTIVE_BROKERS = "interactive_brokers"


@dataclass(frozen=True, slots=True)
class CredentialField:
    name: str
    label: str
    secret: bool
    help_text: str = ""


@dataclass(slots=True)
class Broker:
    """Catalog entry describing a supported venue and its credential schema."""

    id: UUID
    code: str
    name: str
    description: str
    credential_fields: list[CredentialField]
    capabilities: dict[str, Any]
    supports_paper: bool
    supports_live: bool
    is_active: bool = True
    created_at: datetime = field(default_factory=utc_now)

    def validate_credentials(self, credentials: dict[str, str]) -> dict[str, str]:
        cleaned: dict[str, str] = {}
        known = {f.name for f in self.credential_fields}
        unknown = set(credentials) - known
        if unknown:
            raise ValidationFailed(f"unknown credential fields: {', '.join(sorted(unknown))}")
        for spec in self.credential_fields:
            value = (credentials.get(spec.name) or "").strip()
            if not value:
                raise ValidationFailed(f"credential field '{spec.label}' is required")
            if len(value) > 2000:
                raise ValidationFailed(f"credential field '{spec.label}' is too long")
            cleaned[spec.name] = value
        return cleaned


class ConnectionStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"
    DISABLED = "disabled"


@dataclass(slots=True)
class BrokerConnection:
    id: UUID
    organization_id: TenantId
    broker_id: UUID
    broker_code: str
    name: str
    credential_ciphertext: str
    credential_wrapped_dek: str
    key_version: int
    status: ConnectionStatus = ConnectionStatus.PENDING
    last_verified_at: datetime | None = None
    failure_reason: str | None = None
    created_by: UserId | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    deleted_at: datetime | None = None
    version: int = 1

    @classmethod
    def create(
        cls,
        *,
        organization_id: TenantId,
        broker: Broker,
        name: str,
        credential_ciphertext: str,
        credential_wrapped_dek: str,
        key_version: int,
        created_by: UserId,
        connection_id: UUID,
    ) -> BrokerConnection:
        cleaned = name.strip()
        if not cleaned:
            raise ValidationFailed("connection name is required")
        return cls(
            id=connection_id,
            organization_id=organization_id,
            broker_id=broker.id,
            broker_code=broker.code,
            name=cleaned,
            credential_ciphertext=credential_ciphertext,
            credential_wrapped_dek=credential_wrapped_dek,
            key_version=key_version,
            created_by=created_by,
        )

    def mark_verified(self) -> None:
        self.status = ConnectionStatus.VERIFIED
        self.last_verified_at = utc_now()
        self.failure_reason = None
        self.updated_at = utc_now()

    def mark_failed(self, reason: str) -> None:
        self.status = ConnectionStatus.FAILED
        self.failure_reason = reason[:300]
        self.updated_at = utc_now()

    def disable(self) -> None:
        if self.status is ConnectionStatus.DISABLED:
            raise ConflictError("connection is already disabled")
        self.status = ConnectionStatus.DISABLED
        self.updated_at = utc_now()

    def soft_delete(self) -> None:
        self.deleted_at = utc_now()
        self.status = ConnectionStatus.DISABLED
        self.updated_at = utc_now()

    def rotate_credentials(self, *, ciphertext: str, wrapped_dek: str, key_version: int) -> None:
        self.credential_ciphertext = ciphertext
        self.credential_wrapped_dek = wrapped_dek
        self.key_version = key_version
        self.status = ConnectionStatus.PENDING
        self.updated_at = utc_now()


class AccountMode(StrEnum):
    PAPER = "paper"
    LIVE = "live"


class AccountStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"


@dataclass(slots=True)
class TradingAccount:
    id: AccountId
    organization_id: TenantId
    connection_id: UUID
    external_account_id: str
    name: str
    mode: AccountMode
    base_currency: str
    cash_balance: Decimal
    starting_balance: Decimal
    equity: Decimal
    status: AccountStatus = AccountStatus.ACTIVE
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    version: int = 1

    @classmethod
    def open(
        cls,
        *,
        organization_id: TenantId,
        connection_id: UUID,
        external_account_id: str,
        name: str,
        mode: AccountMode,
        base_currency: str,
        starting_balance: Decimal,
    ) -> TradingAccount:
        if starting_balance < 0:
            raise ValidationFailed("starting balance cannot be negative")
        if len(base_currency) != 3:
            raise ValidationFailed("base currency must be an ISO-4217 code")
        return cls(
            id=AccountId(uuid4()),
            organization_id=organization_id,
            connection_id=connection_id,
            external_account_id=external_account_id,
            name=name.strip() or "Account",
            mode=mode,
            base_currency=base_currency.upper(),
            cash_balance=starting_balance,
            starting_balance=starting_balance,
            equity=starting_balance,
        )

    def close(self) -> None:
        if self.status is AccountStatus.CLOSED:
            raise ConflictError("account is already closed")
        self.status = AccountStatus.CLOSED
        self.updated_at = utc_now()

    def apply_cash_delta(self, delta: Decimal) -> None:
        self.cash_balance += delta
        self.updated_at = utc_now()

    def set_equity(self, equity: Decimal) -> None:
        self.equity = equity
        self.updated_at = utc_now()
