"""Strategy management: definitions, versions, uploads, run lifecycle, logs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.billing.application.service import SubscriptionService
from algo_platform.modules.brokerage.infrastructure.repositories import (
    SqlBrokerConnectionRepository,
    SqlTradingAccountRepository,
)
from algo_platform.modules.instruments.application.venue_directory import (
    VenueInstrumentDirectory,
)
from algo_platform.modules.organizations.application.policy import OrganizationPolicy
from algo_platform.modules.risk.application.service import RiskService
from algo_platform.modules.strategies.builtin.registry import (
    BUILTIN_MANIFESTS,
    is_builtin,
)
from algo_platform.modules.strategies.domain.strategies import (
    ACTIVE_RUN_STATES,
    RunState,
    Strategy,
    StrategyRun,
    StrategyStatus,
    StrategyVersion,
    VersionSource,
)
from algo_platform.modules.strategies.infrastructure.artifact_store import (
    ArtifactStore,
    validate_strategy_source,
)
from algo_platform.modules.strategies.infrastructure.models import (
    StrategyLogModel,
    StrategyModel,
    StrategyRunModel,
    StrategyVersionModel,
)
from algo_platform.shared.domain.errors import (
    ConflictError,
    NotFoundError,
    ValidationFailed,
)
from algo_platform.shared.domain.types import (
    AccountId,
    StrategyRunId,
    TenantId,
    UserId,
    utc_now,
)
from algo_platform.shared.infrastructure.outbox import enqueue_engine_command
from algo_platform.shared.infrastructure.redis_gateway import RedisGateway

logger = structlog.get_logger(__name__)

@dataclass(frozen=True, slots=True)
class StrategyDTO:
    id: UUID
    name: str
    description: str
    tags: list[str]
    status: str
    created_at: datetime
    updated_at: datetime
    latest_version: int
    active_runs: int


@dataclass(frozen=True, slots=True)
class StrategyVersionDTO:
    id: UUID
    strategy_id: UUID
    version: int
    source: str
    entry_point: str
    checksum: str
    manifest: dict[str, Any]
    approved_for_live: bool
    created_at: datetime


@dataclass(frozen=True, slots=True)
class StrategyRunDTO:
    id: UUID
    strategy_id: UUID
    strategy_name: str
    strategy_version_id: UUID
    strategy_version: int
    account_id: UUID
    mode: str
    state: str
    parameters: dict[str, Any]
    instrument_ids: list[str]
    timeframe: str
    started_at: datetime | None
    stopped_at: datetime | None
    last_heartbeat_at: datetime | None
    error: str | None
    stats: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class StrategyLogDTO:
    id: UUID
    level: str
    message: str
    context: dict[str, Any]
    logged_at: datetime


def _strategy_entity(model: StrategyModel) -> Strategy:
    return Strategy(
        id=model.id,
        organization_id=TenantId(model.organization_id),
        name=model.name,
        description=model.description,
        tags=list(model.tags),
        status=StrategyStatus(model.status),
        created_by=UserId(model.created_by) if model.created_by else None,
        created_at=model.created_at,
        updated_at=model.updated_at,
        deleted_at=model.deleted_at,
        version=model.version,
    )


def _version_entity(model: StrategyVersionModel) -> StrategyVersion:
    return StrategyVersion(
        id=model.id,
        strategy_id=model.strategy_id,
        organization_id=TenantId(model.organization_id),
        version=model.version,
        source=VersionSource(model.source),
        entry_point=model.entry_point,
        artifact_path=model.artifact_path,
        checksum=model.checksum,
        manifest=dict(model.manifest),
        approved_for_live=model.approved_for_live,
        created_by=UserId(model.created_by) if model.created_by else None,
        created_at=model.created_at,
    )


def run_entity(model: StrategyRunModel) -> StrategyRun:
    return StrategyRun(
        id=StrategyRunId(model.id),
        organization_id=TenantId(model.organization_id),
        strategy_id=model.strategy_id,
        strategy_version_id=model.strategy_version_id,
        account_id=AccountId(model.account_id),
        mode=model.mode,
        state=RunState(model.state),
        parameters=dict(model.parameters),
        instrument_ids=[UUID(i) for i in model.instrument_ids],
        timeframe=model.timeframe,
        created_by=UserId(model.created_by) if model.created_by else None,
        started_at=model.started_at,
        stopped_at=model.stopped_at,
        last_heartbeat_at=model.last_heartbeat_at,
        error=model.error,
        stats=dict(model.stats),
        created_at=model.created_at,
        updated_at=model.updated_at,
        version=model.version,
    )


async def count_active_runs_for(session: AsyncSession, organization_id: TenantId) -> int:
    """Public facade: number of active strategy runs for an organization."""
    count = (
        await session.execute(
            select(func.count())
            .select_from(StrategyRunModel)
            .where(
                StrategyRunModel.organization_id == organization_id,
                StrategyRunModel.state.in_([s.value for s in ACTIVE_RUN_STATES]),
            )
        )
    ).scalar_one()
    return int(count)


def apply_run(model: StrategyRunModel, run: StrategyRun) -> None:
    model.state = run.state.value
    model.started_at = run.started_at
    model.stopped_at = run.stopped_at
    model.last_heartbeat_at = run.last_heartbeat_at
    model.error = run.error
    model.stats = dict(run.stats)
    model.updated_at = utc_now()
    model.version = run.version


class StrategyService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        redis: RedisGateway,
        billing: SubscriptionService,
        risk: RiskService,
        artifacts: ArtifactStore,
        live_market_data_available: bool = False,
    ) -> None:
        self._session = session
        self._redis = redis
        self._billing = billing
        self._risk = risk
        self._artifacts = artifacts
        self._live_market_data_available = live_market_data_available

    # -- strategy definitions --------------------------------------------------

    async def list_strategies(self, organization_id: TenantId) -> list[StrategyDTO]:
        rows = (
            (
                await self._session.execute(
                    select(StrategyModel)
                    .where(
                        StrategyModel.organization_id == organization_id,
                        StrategyModel.deleted_at.is_(None),
                    )
                    .order_by(StrategyModel.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        dtos: list[StrategyDTO] = []
        for row in rows:
            dtos.append(await self._strategy_dto(row))
        return dtos

    async def _strategy_dto(self, model: StrategyModel) -> StrategyDTO:
        latest = (
            await self._session.execute(
                select(func.coalesce(func.max(StrategyVersionModel.version), 0)).where(
                    StrategyVersionModel.strategy_id == model.id
                )
            )
        ).scalar_one()
        active_runs = (
            await self._session.execute(
                select(func.count())
                .select_from(StrategyRunModel)
                .where(
                    StrategyRunModel.strategy_id == model.id,
                    StrategyRunModel.state.in_([s.value for s in ACTIVE_RUN_STATES]),
                )
            )
        ).scalar_one()
        return StrategyDTO(
            id=model.id,
            name=model.name,
            description=model.description,
            tags=list(model.tags),
            status=model.status,
            created_at=model.created_at,
            updated_at=model.updated_at,
            latest_version=int(latest),
            active_runs=int(active_runs),
        )

    async def get_strategy(self, organization_id: TenantId, strategy_id: UUID) -> StrategyDTO:
        model = await self._get_strategy_model(organization_id, strategy_id)
        return await self._strategy_dto(model)

    async def _get_strategy_model(
        self, organization_id: TenantId, strategy_id: UUID
    ) -> StrategyModel:
        model = await self._session.get(StrategyModel, strategy_id)
        if (
            model is None
            or model.organization_id != organization_id
            or model.deleted_at is not None
        ):
            raise NotFoundError("strategy not found")
        return model

    async def create_strategy(
        self,
        organization_id: TenantId,
        *,
        name: str,
        description: str,
        tags: list[str],
        created_by: UserId,
        builtin_entry_point: str | None = None,
    ) -> StrategyDTO:
        strategy = Strategy.create(
            organization_id=organization_id,
            name=name,
            description=description,
            tags=tags,
            created_by=created_by,
        )
        model = StrategyModel(
            id=strategy.id,
            organization_id=strategy.organization_id,
            name=strategy.name,
            description=strategy.description,
            tags=list(strategy.tags),
            status=strategy.status.value,
            created_by=strategy.created_by,
            created_at=strategy.created_at,
            updated_at=strategy.updated_at,
            version=strategy.version,
        )
        self._session.add(model)
        await self._session.flush()
        if builtin_entry_point:
            await self.create_builtin_version(
                organization_id,
                strategy_id=strategy.id,
                entry_point=builtin_entry_point,
                created_by=created_by,
            )
            model.status = StrategyStatus.ACTIVE.value
            await self._session.flush()
        return await self._strategy_dto(model)

    async def update_strategy(
        self,
        organization_id: TenantId,
        strategy_id: UUID,
        *,
        name: str | None,
        description: str | None,
        tags: list[str] | None,
        status: str | None,
    ) -> StrategyDTO:
        model = await self._get_strategy_model(organization_id, strategy_id)
        entity = _strategy_entity(model)
        entity.update_details(name=name, description=description, tags=tags)
        if status is not None:
            if status == StrategyStatus.ACTIVE.value:
                entity.activate()
            elif status == StrategyStatus.ARCHIVED.value:
                entity.archive()
            elif status == StrategyStatus.DRAFT.value:
                entity.status = StrategyStatus.DRAFT
            else:
                raise ValidationFailed("status must be draft, active, or archived")
        model.name = entity.name
        model.description = entity.description
        model.tags = list(entity.tags)
        model.status = entity.status.value
        model.updated_at = utc_now()
        model.version = entity.version + 1
        await self._session.flush()
        return await self._strategy_dto(model)

    async def delete_strategy(self, organization_id: TenantId, strategy_id: UUID) -> None:
        model = await self._get_strategy_model(organization_id, strategy_id)
        active = (
            await self._session.execute(
                select(func.count())
                .select_from(StrategyRunModel)
                .where(
                    StrategyRunModel.strategy_id == strategy_id,
                    StrategyRunModel.state.in_([s.value for s in ACTIVE_RUN_STATES]),
                )
            )
        ).scalar_one()
        if int(active) > 0:
            raise ConflictError("stop active runs before deleting the strategy")
        model.deleted_at = utc_now()
        model.status = StrategyStatus.ARCHIVED.value
        await self._session.flush()

    async def duplicate_strategy(
        self,
        organization_id: TenantId,
        strategy_id: UUID,
        *,
        created_by: UserId,
    ) -> StrategyDTO:
        source_model = await self._get_strategy_model(organization_id, strategy_id)
        copy = await self.create_strategy(
            organization_id,
            name=f"{source_model.name} (copy)",
            description=source_model.description,
            tags=list(source_model.tags),
            created_by=created_by,
        )
        versions = (
            (
                await self._session.execute(
                    select(StrategyVersionModel)
                    .where(StrategyVersionModel.strategy_id == strategy_id)
                    .order_by(StrategyVersionModel.version)
                )
            )
            .scalars()
            .all()
        )
        for version_model in versions:
            self._session.add(
                StrategyVersionModel(
                    id=uuid4(),
                    strategy_id=copy.id,
                    organization_id=organization_id,
                    version=version_model.version,
                    source=version_model.source,
                    entry_point=version_model.entry_point,
                    artifact_path=version_model.artifact_path,
                    checksum=version_model.checksum,
                    manifest=dict(version_model.manifest),
                    approved_for_live=False,
                    created_by=created_by,
                    created_at=utc_now(),
                )
            )
        await self._session.flush()
        return await self.get_strategy(organization_id, copy.id)

    # -- versions ------------------------------------------------------------------

    def builtin_catalog(self) -> list[dict[str, Any]]:
        return [dict(manifest) for manifest in BUILTIN_MANIFESTS.values()]

    async def list_versions(
        self, organization_id: TenantId, strategy_id: UUID
    ) -> list[StrategyVersionDTO]:
        await self._get_strategy_model(organization_id, strategy_id)
        rows = (
            (
                await self._session.execute(
                    select(StrategyVersionModel)
                    .where(StrategyVersionModel.strategy_id == strategy_id)
                    .order_by(StrategyVersionModel.version.desc())
                )
            )
            .scalars()
            .all()
        )
        return [self._version_dto(m) for m in rows]

    @staticmethod
    def _version_dto(model: StrategyVersionModel) -> StrategyVersionDTO:
        return StrategyVersionDTO(
            id=model.id,
            strategy_id=model.strategy_id,
            version=model.version,
            source=model.source,
            entry_point=model.entry_point,
            checksum=model.checksum,
            manifest=dict(model.manifest),
            approved_for_live=model.approved_for_live,
            created_at=model.created_at,
        )

    async def _next_version_number(self, strategy_id: UUID) -> int:
        latest = (
            await self._session.execute(
                select(func.coalesce(func.max(StrategyVersionModel.version), 0)).where(
                    StrategyVersionModel.strategy_id == strategy_id
                )
            )
        ).scalar_one()
        return int(latest) + 1

    async def create_builtin_version(
        self,
        organization_id: TenantId,
        *,
        strategy_id: UUID,
        entry_point: str,
        created_by: UserId,
    ) -> StrategyVersionDTO:
        await self._get_strategy_model(organization_id, strategy_id)
        if not is_builtin(entry_point):
            raise ValidationFailed("unknown builtin strategy entry point")
        manifest = dict(BUILTIN_MANIFESTS[entry_point])
        model = StrategyVersionModel(
            id=uuid4(),
            strategy_id=strategy_id,
            organization_id=organization_id,
            version=await self._next_version_number(strategy_id),
            source=VersionSource.BUILTIN.value,
            entry_point=entry_point,
            artifact_path=None,
            checksum="builtin",
            manifest=manifest,
            approved_for_live=True,
            created_by=created_by,
            created_at=utc_now(),
        )
        self._session.add(model)
        await self._session.flush()
        return self._version_dto(model)

    async def create_uploaded_version(
        self,
        organization_id: TenantId,
        *,
        strategy_id: UUID,
        source_code: str,
        entry_class: str,
        parameters: list[dict[str, Any]],
        created_by: UserId,
    ) -> StrategyVersionDTO:
        await self._get_strategy_model(organization_id, strategy_id)
        validated = validate_strategy_source(source_code, entry_class=entry_class)
        artifact_path = self._artifacts.save(checksum=validated.checksum, source=source_code)
        manifest = {
            "name": entry_class,
            "entry_point": entry_class,
            "required_data": ["candles"],
            "parameters": parameters,
        }
        model = StrategyVersionModel(
            id=uuid4(),
            strategy_id=strategy_id,
            organization_id=organization_id,
            version=await self._next_version_number(strategy_id),
            source=VersionSource.UPLOADED.value,
            entry_point=entry_class,
            artifact_path=artifact_path,
            checksum=validated.checksum,
            manifest=manifest,
            approved_for_live=False,
            created_by=created_by,
            created_at=utc_now(),
        )
        self._session.add(model)
        await self._session.flush()
        logger.info(
            "strategies.version_uploaded",
            strategy_id=str(strategy_id),
            checksum=validated.checksum,
        )
        return self._version_dto(model)

    # -- runs ----------------------------------------------------------------------

    async def create_run(
        self,
        organization_id: TenantId,
        *,
        strategy_version_id: UUID,
        account_id: AccountId,
        parameters: dict[str, Any],
        instrument_ids: list[UUID],
        timeframe: str,
        created_by: UserId,
    ) -> StrategyRunDTO:
        version_model = await self._session.get(StrategyVersionModel, strategy_version_id)
        if version_model is None or version_model.organization_id != organization_id:
            raise NotFoundError("strategy version not found")
        version = _version_entity(version_model)

        account = await SqlTradingAccountRepository(self._session).get(organization_id, account_id)
        if account is None:
            raise NotFoundError("trading account not found")
        if account.status.value != "active":
            raise ConflictError("trading account is closed")
        mode = account.mode.value
        if mode == "live":
            if not self._live_market_data_available:
                raise ConflictError(
                    "live strategy runs require a verified live market-data source"
                )
            await self._billing.require_feature(organization_id, feature="live_trading")
            organization_policy = OrganizationPolicy(self._session)
            if not await organization_policy.live_trading_enabled(organization_id):
                raise ConflictError(
                    "live trading is disabled in organization settings"
                )
            if not version.approved_for_live:
                raise ConflictError("this strategy version is not approved for live trading")
            connection = await SqlBrokerConnectionRepository(self._session).get(
                organization_id, account.connection_id
            )
            if connection is None or connection.status.value != "verified":
                raise ConflictError("the live broker connection is not verified")
            venue_directory = VenueInstrumentDirectory(self._session)
            for instrument_id in instrument_ids:
                try:
                    await venue_directory.resolve(
                        broker_id=connection.broker_id,
                        instrument_id=instrument_id,
                    )
                except NotFoundError as error:
                    raise ConflictError(
                        "a selected instrument is not mapped for the live broker",
                        details={"instrument_id": str(instrument_id)},
                    ) from error

        active_count = (
            await self._session.execute(
                select(func.count())
                .select_from(StrategyRunModel)
                .where(
                    StrategyRunModel.organization_id == organization_id,
                    StrategyRunModel.state.in_([s.value for s in ACTIVE_RUN_STATES]),
                )
            )
        ).scalar_one()
        await self._billing.require_within_limit(
            organization_id, metric="max_active_strategies", current=int(active_count)
        )
        switch = await self._risk.active_kill_switch(organization_id, account_id=account_id)
        if switch is not None:
            raise ConflictError("a kill switch is engaged; cannot start strategy runs")

        resolved = version.resolve_parameters(parameters)
        run = StrategyRun.create(
            organization_id=organization_id,
            strategy_id=version.strategy_id,
            strategy_version_id=version.id,
            account_id=account_id,
            mode=mode,
            parameters=resolved,
            instrument_ids=instrument_ids,
            timeframe=timeframe,
            created_by=created_by,
        )
        self._session.add(
            StrategyRunModel(
                id=run.id,
                organization_id=run.organization_id,
                strategy_id=run.strategy_id,
                strategy_version_id=run.strategy_version_id,
                account_id=run.account_id,
                mode=run.mode,
                state=run.state.value,
                parameters=dict(run.parameters),
                instrument_ids=[str(i) for i in run.instrument_ids],
                timeframe=run.timeframe,
                created_by=run.created_by,
                stats={},
                created_at=run.created_at,
                updated_at=run.updated_at,
                version=run.version,
            )
        )
        await self._session.flush()
        return await self.get_run(organization_id, run.id)

    async def list_runs(
        self,
        organization_id: TenantId,
        *,
        strategy_id: UUID | None = None,
        active_only: bool = False,
        limit: int = 100,
    ) -> list[StrategyRunDTO]:
        stmt = select(StrategyRunModel).where(StrategyRunModel.organization_id == organization_id)
        if strategy_id is not None:
            stmt = stmt.where(StrategyRunModel.strategy_id == strategy_id)
        if active_only:
            stmt = stmt.where(StrategyRunModel.state.in_([s.value for s in ACTIVE_RUN_STATES]))
        stmt = stmt.order_by(StrategyRunModel.created_at.desc()).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [await self._run_dto(m) for m in rows]

    async def get_run(
        self, organization_id: TenantId, run_id: StrategyRunId | UUID
    ) -> StrategyRunDTO:
        model = await self._session.get(StrategyRunModel, run_id)
        if model is None or model.organization_id != organization_id:
            raise NotFoundError("strategy run not found")
        return await self._run_dto(model)

    async def _run_dto(self, model: StrategyRunModel) -> StrategyRunDTO:
        strategy = await self._session.get(StrategyModel, model.strategy_id)
        version = await self._session.get(StrategyVersionModel, model.strategy_version_id)
        return StrategyRunDTO(
            id=model.id,
            strategy_id=model.strategy_id,
            strategy_name=strategy.name if strategy else "?",
            strategy_version_id=model.strategy_version_id,
            strategy_version=version.version if version else 0,
            account_id=model.account_id,
            mode=model.mode,
            state=model.state,
            parameters=dict(model.parameters),
            instrument_ids=list(model.instrument_ids),
            timeframe=model.timeframe,
            started_at=model.started_at,
            stopped_at=model.stopped_at,
            last_heartbeat_at=model.last_heartbeat_at,
            error=model.error,
            stats=dict(model.stats),
            created_at=model.created_at,
        )

    async def _transition_run(
        self,
        organization_id: TenantId,
        run_id: UUID,
        action: str,
    ) -> StrategyRunDTO:
        model = await self._session.get(StrategyRunModel, run_id)
        if model is None or model.organization_id != organization_id:
            raise NotFoundError("strategy run not found")
        run = run_entity(model)
        if action == "start":
            switch = await self._risk.active_kill_switch(
                organization_id, account_id=run.account_id, strategy_run_id=run.id
            )
            if switch is not None:
                raise ConflictError("a kill switch is engaged; cannot start the run")
            run.request_start()
        elif action == "stop":
            run.request_stop()
        elif action == "pause":
            run.pause()
        elif action == "resume":
            run.request_start()
        else:
            raise ValidationFailed(f"unknown run action: {action}")
        apply_run(model, run)
        await self._session.flush()
        await enqueue_engine_command(
            self._session,
            command_type=f"{action}_run",
            aggregate_type="strategy_run",
            aggregate_id=run.id,
            organization_id=organization_id,
            payload={
                "run_id": str(run.id),
                "organization_id": str(organization_id),
            },
        )
        return await self._run_dto(model)

    async def start_run(self, organization_id: TenantId, run_id: UUID) -> StrategyRunDTO:
        return await self._transition_run(organization_id, run_id, "start")

    async def pause_run(self, organization_id: TenantId, run_id: UUID) -> StrategyRunDTO:
        return await self._transition_run(organization_id, run_id, "pause")

    async def resume_run(self, organization_id: TenantId, run_id: UUID) -> StrategyRunDTO:
        return await self._transition_run(organization_id, run_id, "resume")

    async def stop_run(self, organization_id: TenantId, run_id: UUID) -> StrategyRunDTO:
        return await self._transition_run(organization_id, run_id, "stop")

    async def list_logs(
        self,
        organization_id: TenantId,
        run_id: UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[StrategyLogDTO]:
        model = await self._session.get(StrategyRunModel, run_id)
        if model is None or model.organization_id != organization_id:
            raise NotFoundError("strategy run not found")
        rows = (
            (
                await self._session.execute(
                    select(StrategyLogModel)
                    .where(StrategyLogModel.run_id == run_id)
                    .order_by(StrategyLogModel.logged_at.desc())
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return [
            StrategyLogDTO(
                id=r.id,
                level=r.level,
                message=r.message,
                context=dict(r.context),
                logged_at=r.logged_at,
            )
            for r in rows
        ]

    async def count_active_runs(self, organization_id: TenantId) -> int:
        count = (
            await self._session.execute(
                select(func.count())
                .select_from(StrategyRunModel)
                .where(
                    StrategyRunModel.organization_id == organization_id,
                    StrategyRunModel.state.in_([s.value for s in ACTIVE_RUN_STATES]),
                )
            )
        ).scalar_one()
        return int(count)
