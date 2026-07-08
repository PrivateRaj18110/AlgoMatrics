"""Broker connection lifecycle: add, verify, rotate credentials, remove."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import structlog

from algo_platform.modules.billing.application.service import SubscriptionService
from algo_platform.modules.brokerage.domain.brokers import (
    AccountMode,
    Broker,
    BrokerCode,
    BrokerConnection,
    TradingAccount,
)
from algo_platform.modules.brokerage.infrastructure.repositories import (
    SqlBrokerCatalogRepository,
    SqlBrokerConnectionRepository,
    SqlTradingAccountRepository,
)
from algo_platform.modules.brokerage.infrastructure.verifiers import (
    BrokerVerifier,
    VerificationResult,
)
from algo_platform.shared.domain.errors import (
    ConflictError,
    NotFoundError,
    ValidationFailed,
)
from algo_platform.shared.domain.types import AccountId, TenantId, UserId
from algo_platform.shared.infrastructure.encryption import CredentialCipher, EncryptedSecret

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class BrokerCatalogDTO:
    id: UUID
    code: str
    name: str
    description: str
    credential_fields: list[dict[str, Any]]
    capabilities: dict[str, Any]
    supports_paper: bool
    supports_live: bool


@dataclass(frozen=True, slots=True)
class ConnectionDTO:
    id: UUID
    broker_code: str
    broker_name: str
    name: str
    status: str
    last_verified_at: datetime | None
    failure_reason: str | None
    created_at: datetime
    accounts: list[AccountDTO]


@dataclass(frozen=True, slots=True)
class AccountDTO:
    id: UUID
    connection_id: UUID
    external_account_id: str
    name: str
    mode: str
    base_currency: str
    cash_balance: Decimal
    starting_balance: Decimal
    equity: Decimal
    status: str


def encrypt_connection_credentials(
    cipher: CredentialCipher, connection_id: UUID, credentials: dict[str, str]
) -> EncryptedSecret:
    payload = json.dumps(credentials, sort_keys=True).encode("utf-8")
    return cipher.encrypt(payload, aad=f"broker-connection:{connection_id}".encode())


def decrypt_connection_credentials(
    cipher: CredentialCipher, connection: BrokerConnection
) -> dict[str, str]:
    plaintext = cipher.decrypt(
        EncryptedSecret(
            ciphertext_b64=connection.credential_ciphertext,
            wrapped_dek_b64=connection.credential_wrapped_dek,
            key_version=connection.key_version,
        ),
        aad=f"broker-connection:{connection.id}".encode(),
    )
    loaded = json.loads(plaintext.decode("utf-8"))
    return {str(k): str(v) for k, v in loaded.items()}


def _account_dto(account: TradingAccount) -> AccountDTO:
    return AccountDTO(
        id=account.id,
        connection_id=account.connection_id,
        external_account_id=account.external_account_id,
        name=account.name,
        mode=account.mode.value,
        base_currency=account.base_currency,
        cash_balance=account.cash_balance,
        starting_balance=account.starting_balance,
        equity=account.equity,
        status=account.status.value,
    )


class BrokerageService:
    def __init__(
        self,
        *,
        catalog: SqlBrokerCatalogRepository,
        connections: SqlBrokerConnectionRepository,
        accounts: SqlTradingAccountRepository,
        verifiers: dict[str, BrokerVerifier],
        cipher: CredentialCipher,
        billing: SubscriptionService,
    ) -> None:
        self._catalog = catalog
        self._connections = connections
        self._accounts = accounts
        self._verifiers = verifiers
        self._cipher = cipher
        self._billing = billing

    # -- catalog -----------------------------------------------------------

    async def list_brokers(self) -> list[BrokerCatalogDTO]:
        brokers = await self._catalog.list_active()
        return [
            BrokerCatalogDTO(
                id=b.id,
                code=b.code,
                name=b.name,
                description=b.description,
                credential_fields=[
                    {
                        "name": f.name,
                        "label": f.label,
                        "secret": f.secret,
                        "help_text": f.help_text,
                    }
                    for f in b.credential_fields
                ],
                capabilities=dict(b.capabilities),
                supports_paper=b.supports_paper,
                supports_live=b.supports_live,
            )
            for b in brokers
        ]

    # -- connections ---------------------------------------------------------

    async def list_connections(self, organization_id: TenantId) -> list[ConnectionDTO]:
        connections = await self._connections.list_for_organization(organization_id)
        brokers = {b.id: b for b in await self._catalog.list_active()}
        dtos: list[ConnectionDTO] = []
        for connection in connections:
            accounts = await self._accounts.list_for_connection(connection.id)
            broker = brokers.get(connection.broker_id)
            dtos.append(
                ConnectionDTO(
                    id=connection.id,
                    broker_code=connection.broker_code,
                    broker_name=broker.name if broker else connection.broker_code,
                    name=connection.name,
                    status=connection.status.value,
                    last_verified_at=connection.last_verified_at,
                    failure_reason=connection.failure_reason,
                    created_at=connection.created_at,
                    accounts=[_account_dto(a) for a in accounts],
                )
            )
        return dtos

    async def get_connection(self, organization_id: TenantId, connection_id: UUID) -> ConnectionDTO:
        connection = await self._connections.get(organization_id, connection_id)
        if connection is None:
            raise NotFoundError("broker connection not found")
        broker = await self._catalog.get(connection.broker_id)
        accounts = await self._accounts.list_for_connection(connection.id)
        return ConnectionDTO(
            id=connection.id,
            broker_code=connection.broker_code,
            broker_name=broker.name if broker else connection.broker_code,
            name=connection.name,
            status=connection.status.value,
            last_verified_at=connection.last_verified_at,
            failure_reason=connection.failure_reason,
            created_at=connection.created_at,
            accounts=[_account_dto(a) for a in accounts],
        )

    async def add_connection(
        self,
        organization_id: TenantId,
        *,
        broker_code: str,
        name: str,
        credentials: dict[str, str],
        created_by: UserId,
        account_mode: str = "paper",
    ) -> ConnectionDTO:
        broker = await self._catalog.get_by_code(broker_code)
        if broker is None or not broker.is_active:
            raise NotFoundError("broker not found or disabled")
        current = await self._connections.count_for_organization(organization_id)
        await self._billing.require_within_limit(
            organization_id, metric="max_broker_connections", current=current
        )
        mode = AccountMode(account_mode)
        if mode is AccountMode.LIVE:
            if not broker.supports_live or broker.code == BrokerCode.PAPER.value:
                raise ValidationFailed("this broker does not support live accounts")
            await self._billing.require_feature(organization_id, feature="live_trading")
        if mode is AccountMode.PAPER and not broker.supports_paper:
            raise ValidationFailed(
                "this broker does not support paper accounts; use the Paper Trading broker"
            )
        if await self._connections.name_exists(organization_id, name):
            raise ConflictError("a connection with this name already exists")

        cleaned = broker.validate_credentials(credentials)
        connection_id = uuid4()
        secret = self._encrypt_credentials(connection_id, cleaned)
        connection = BrokerConnection.create(
            organization_id=organization_id,
            broker=broker,
            name=name,
            credential_ciphertext=secret.ciphertext_b64,
            credential_wrapped_dek=secret.wrapped_dek_b64,
            key_version=secret.key_version,
            created_by=created_by,
            connection_id=connection_id,
        )

        result = await self._verify_with_adapter(broker, cleaned)
        if result.ok:
            connection.mark_verified()
        else:
            connection.mark_failed(result.message)
        await self._connections.add(connection)

        if result.ok:
            await self._ensure_account(connection, broker, cleaned, mode, result)
        logger.info(
            "brokerage.connection_added",
            organization_id=str(organization_id),
            broker=broker.code,
            verified=result.ok,
        )
        return await self.get_connection(organization_id, connection.id)

    async def _ensure_account(
        self,
        connection: BrokerConnection,
        broker: Broker,
        credentials: dict[str, str],
        mode: AccountMode,
        result: VerificationResult,
    ) -> None:
        existing = await self._accounts.list_for_connection(connection.id)
        if existing:
            return
        starting_balance = Decimal("0")
        currency = result.base_currency
        if broker.code == BrokerCode.PAPER.value:
            starting_balance = Decimal(credentials.get("starting_balance", "1000000"))
            currency = (credentials.get("base_currency") or "INR").upper()
        account = TradingAccount.open(
            organization_id=connection.organization_id,
            connection_id=connection.id,
            external_account_id=result.external_account_id,
            name=f"{connection.name} {mode.value}",
            mode=mode,
            base_currency=currency,
            starting_balance=starting_balance,
        )
        await self._accounts.add(account)

    async def update_connection(
        self,
        organization_id: TenantId,
        connection_id: UUID,
        *,
        name: str | None,
        credentials: dict[str, str] | None,
    ) -> ConnectionDTO:
        connection = await self._connections.get(organization_id, connection_id)
        if connection is None:
            raise NotFoundError("broker connection not found")
        if name is not None and name.strip() and name.strip() != connection.name:
            if await self._connections.name_exists(organization_id, name):
                raise ConflictError("a connection with this name already exists")
            connection.name = name.strip()
        if credentials is not None:
            broker = await self._catalog.get(connection.broker_id)
            if broker is None:
                raise NotFoundError("broker no longer exists")
            cleaned = broker.validate_credentials(credentials)
            secret = self._encrypt_credentials(connection.id, cleaned)
            connection.rotate_credentials(
                ciphertext=secret.ciphertext_b64,
                wrapped_dek=secret.wrapped_dek_b64,
                key_version=secret.key_version,
            )
            result = await self._verify_with_adapter(broker, cleaned)
            if result.ok:
                connection.mark_verified()
            else:
                connection.mark_failed(result.message)
        await self._connections.save(connection)
        return await self.get_connection(organization_id, connection_id)

    async def verify_connection(
        self, organization_id: TenantId, connection_id: UUID
    ) -> ConnectionDTO:
        connection = await self._connections.get(organization_id, connection_id)
        if connection is None:
            raise NotFoundError("broker connection not found")
        broker = await self._catalog.get(connection.broker_id)
        if broker is None:
            raise NotFoundError("broker no longer exists")
        credentials = self.decrypt_credentials(connection)
        result = await self._verify_with_adapter(broker, credentials)
        if result.ok:
            connection.mark_verified()
        else:
            connection.mark_failed(result.message)
        await self._connections.save(connection)
        return await self.get_connection(organization_id, connection_id)

    async def remove_connection(self, organization_id: TenantId, connection_id: UUID) -> None:
        connection = await self._connections.get(organization_id, connection_id)
        if connection is None:
            raise NotFoundError("broker connection not found")
        accounts = await self._accounts.list_for_connection(connection.id)
        for account in accounts:
            if account.status.value == "active":
                account.close()
                await self._accounts.save(account)
        connection.soft_delete()
        await self._connections.save(connection)

    # -- accounts ---------------------------------------------------------------

    async def list_accounts(self, organization_id: TenantId) -> list[AccountDTO]:
        accounts = await self._accounts.list_for_organization(organization_id)
        return [_account_dto(a) for a in accounts]

    async def get_account(self, organization_id: TenantId, account_id: AccountId) -> AccountDTO:
        account = await self._accounts.get(organization_id, account_id)
        if account is None:
            raise NotFoundError("trading account not found")
        return _account_dto(account)

    # -- credential handling -------------------------------------------------------

    def _encrypt_credentials(
        self, connection_id: UUID, credentials: dict[str, str]
    ) -> EncryptedSecret:
        return encrypt_connection_credentials(self._cipher, connection_id, credentials)

    def decrypt_credentials(self, connection: BrokerConnection) -> dict[str, str]:
        return decrypt_connection_credentials(self._cipher, connection)

    async def _verify_with_adapter(
        self, broker: Broker, credentials: dict[str, str]
    ) -> VerificationResult:
        verifier = self._verifiers.get(broker.code)
        if verifier is None:
            return VerificationResult(
                ok=False, message=f"no verifier registered for broker '{broker.code}'"
            )
        return await verifier.verify(credentials)
