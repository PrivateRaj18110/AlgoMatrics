from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.brokerage.domain.brokers import (
    AccountMode,
    AccountStatus,
    Broker,
    BrokerConnection,
    ConnectionStatus,
    CredentialField,
    TradingAccount,
)
from algo_platform.modules.brokerage.infrastructure.models import (
    BrokerConnectionModel,
    BrokerModel,
    TradingAccountModel,
)
from algo_platform.shared.domain.types import AccountId, TenantId, UserId, utc_now


def _broker_to_entity(model: BrokerModel) -> Broker:
    return Broker(
        id=model.id,
        code=model.code,
        name=model.name,
        description=model.description,
        credential_fields=[
            CredentialField(
                name=str(f.get("name", "")),
                label=str(f.get("label", f.get("name", ""))),
                secret=bool(f.get("secret", True)),
                help_text=str(f.get("help_text", "")),
            )
            for f in model.credential_fields
        ],
        capabilities=dict(model.capabilities),
        supports_paper=model.supports_paper,
        supports_live=model.supports_live,
        is_active=model.is_active,
        created_at=model.created_at,
    )


class SqlBrokerCatalogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active(self) -> list[Broker]:
        result = await self._session.execute(
            select(BrokerModel).where(BrokerModel.is_active).order_by(BrokerModel.name)
        )
        return [_broker_to_entity(m) for m in result.scalars().all()]

    async def get(self, broker_id: UUID) -> Broker | None:
        model = await self._session.get(BrokerModel, broker_id)
        return _broker_to_entity(model) if model else None

    async def get_by_code(self, code: str) -> Broker | None:
        result = await self._session.execute(
            select(BrokerModel).where(BrokerModel.code == code.strip().lower())
        )
        model = result.scalar_one_or_none()
        return _broker_to_entity(model) if model else None


def _connection_to_entity(model: BrokerConnectionModel) -> BrokerConnection:
    return BrokerConnection(
        id=model.id,
        organization_id=TenantId(model.organization_id),
        broker_id=model.broker_id,
        broker_code=model.broker_code,
        name=model.name,
        credential_ciphertext=model.credential_ciphertext,
        credential_wrapped_dek=model.credential_wrapped_dek,
        key_version=model.key_version,
        status=ConnectionStatus(model.status),
        last_verified_at=model.last_verified_at,
        failure_reason=model.failure_reason,
        created_by=UserId(model.created_by) if model.created_by else None,
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
        version=model.version,
    )


class SqlBrokerConnectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, connection: BrokerConnection) -> None:
        self._session.add(
            BrokerConnectionModel(
                id=connection.id,
                organization_id=connection.organization_id,
                broker_id=connection.broker_id,
                broker_code=connection.broker_code,
                name=connection.name,
                credential_ciphertext=connection.credential_ciphertext,
                credential_wrapped_dek=connection.credential_wrapped_dek,
                key_version=connection.key_version,
                status=connection.status.value,
                last_verified_at=connection.last_verified_at,
                failure_reason=connection.failure_reason,
                created_by=connection.created_by,
                created_at=connection.created_at,
                updated_at=connection.updated_at,
                version=connection.version,
            )
        )
        await self._session.flush()

    async def get(self, organization_id: TenantId, connection_id: UUID) -> BrokerConnection | None:
        model = await self._session.get(BrokerConnectionModel, connection_id)
        if model is None or model.organization_id != organization_id:
            return None
        if model.deleted_at is not None:
            return None
        return _connection_to_entity(model)

    async def get_any(self, connection_id: UUID) -> BrokerConnection | None:
        model = await self._session.get(BrokerConnectionModel, connection_id)
        if model is None or model.deleted_at is not None:
            return None
        return _connection_to_entity(model)

    async def list_for_organization(self, organization_id: TenantId) -> list[BrokerConnection]:
        result = await self._session.execute(
            select(BrokerConnectionModel)
            .where(
                BrokerConnectionModel.organization_id == organization_id,
                BrokerConnectionModel.deleted_at.is_(None),
            )
            .order_by(BrokerConnectionModel.created_at)
        )
        return [_connection_to_entity(m) for m in result.scalars().all()]

    async def count_for_organization(self, organization_id: TenantId) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(BrokerConnectionModel)
            .where(
                BrokerConnectionModel.organization_id == organization_id,
                BrokerConnectionModel.deleted_at.is_(None),
            )
        )
        return int(result.scalar_one())

    async def name_exists(self, organization_id: TenantId, name: str) -> bool:
        result = await self._session.execute(
            select(func.count())
            .select_from(BrokerConnectionModel)
            .where(
                BrokerConnectionModel.organization_id == organization_id,
                BrokerConnectionModel.name == name.strip(),
                BrokerConnectionModel.deleted_at.is_(None),
            )
        )
        return int(result.scalar_one()) > 0

    async def save(self, connection: BrokerConnection) -> None:
        model = await self._session.get(BrokerConnectionModel, connection.id)
        if model is None:
            raise LookupError(f"broker connection {connection.id} not found")
        model.name = connection.name
        model.credential_ciphertext = connection.credential_ciphertext
        model.credential_wrapped_dek = connection.credential_wrapped_dek
        model.key_version = connection.key_version
        model.status = connection.status.value
        model.last_verified_at = connection.last_verified_at
        model.failure_reason = connection.failure_reason
        model.updated_at = utc_now()
        model.deleted_at = connection.deleted_at
        model.version = connection.version + 1
        await self._session.flush()


def _account_to_entity(model: TradingAccountModel) -> TradingAccount:
    return TradingAccount(
        id=AccountId(model.id),
        organization_id=TenantId(model.organization_id),
        connection_id=model.connection_id,
        external_account_id=model.external_account_id,
        name=model.name,
        mode=AccountMode(model.mode),
        base_currency=model.base_currency,
        cash_balance=model.cash_balance,
        starting_balance=model.starting_balance,
        equity=model.equity,
        status=AccountStatus(model.status),
        created_at=model.created_at,
        updated_at=model.updated_at,
        version=model.version,
    )


class SqlTradingAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, account: TradingAccount) -> None:
        self._session.add(
            TradingAccountModel(
                id=account.id,
                organization_id=account.organization_id,
                connection_id=account.connection_id,
                external_account_id=account.external_account_id,
                name=account.name,
                mode=account.mode.value,
                base_currency=account.base_currency,
                cash_balance=account.cash_balance,
                starting_balance=account.starting_balance,
                equity=account.equity,
                status=account.status.value,
                created_at=account.created_at,
                updated_at=account.updated_at,
                version=account.version,
            )
        )
        await self._session.flush()

    async def get(self, organization_id: TenantId, account_id: AccountId) -> TradingAccount | None:
        model = await self._session.get(TradingAccountModel, account_id)
        if model is None or model.organization_id != organization_id:
            return None
        return _account_to_entity(model)

    async def get_any(self, account_id: AccountId) -> TradingAccount | None:
        model = await self._session.get(TradingAccountModel, account_id)
        return _account_to_entity(model) if model else None

    async def list_for_organization(
        self, organization_id: TenantId, *, active_only: bool = False
    ) -> list[TradingAccount]:
        stmt = select(TradingAccountModel).where(
            TradingAccountModel.organization_id == organization_id
        )
        if active_only:
            stmt = stmt.where(TradingAccountModel.status == AccountStatus.ACTIVE.value)
        stmt = stmt.order_by(TradingAccountModel.created_at)
        result = await self._session.execute(stmt)
        return [_account_to_entity(m) for m in result.scalars().all()]

    async def list_for_connection(self, connection_id: UUID) -> list[TradingAccount]:
        result = await self._session.execute(
            select(TradingAccountModel).where(TradingAccountModel.connection_id == connection_id)
        )
        return [_account_to_entity(m) for m in result.scalars().all()]

    async def save(self, account: TradingAccount) -> None:
        model = await self._session.get(TradingAccountModel, account.id)
        if model is None:
            raise LookupError(f"trading account {account.id} not found")
        model.name = account.name
        model.cash_balance = account.cash_balance
        model.equity = account.equity
        model.status = account.status.value
        model.updated_at = utc_now()
        model.version = account.version + 1
        await self._session.flush()
