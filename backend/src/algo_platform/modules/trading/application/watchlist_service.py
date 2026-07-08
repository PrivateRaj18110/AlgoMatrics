from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.billing.application.service import SubscriptionService
from algo_platform.modules.instruments.application.directory import InstrumentDirectory
from algo_platform.modules.trading.infrastructure.models import (
    WatchlistItemModel,
    WatchlistModel,
)
from algo_platform.shared.domain.errors import ConflictError, NotFoundError, ValidationFailed
from algo_platform.shared.domain.types import TenantId, UserId, utc_now


@dataclass(frozen=True, slots=True)
class WatchlistItemDTO:
    id: UUID
    instrument_id: UUID
    symbol: str
    name: str
    sort_order: int


@dataclass(frozen=True, slots=True)
class WatchlistDTO:
    id: UUID
    name: str
    created_at: datetime
    items: list[WatchlistItemDTO]


class WatchlistService:
    def __init__(self, session: AsyncSession, billing: SubscriptionService) -> None:
        self._session = session
        self._billing = billing
        self._instruments = InstrumentDirectory(session)

    async def list(self, organization_id: TenantId) -> list[WatchlistDTO]:
        rows = (
            (
                await self._session.execute(
                    select(WatchlistModel)
                    .where(WatchlistModel.organization_id == organization_id)
                    .order_by(WatchlistModel.created_at)
                )
            )
            .scalars()
            .all()
        )
        return [await self._to_dto(row) for row in rows]

    async def get(self, organization_id: TenantId, watchlist_id: UUID) -> WatchlistDTO:
        model = await self._get_model(organization_id, watchlist_id)
        return await self._to_dto(model)

    async def create(
        self, organization_id: TenantId, *, name: str, created_by: UserId
    ) -> WatchlistDTO:
        cleaned = name.strip()
        if not cleaned:
            raise ValidationFailed("watchlist name is required")
        count = int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(WatchlistModel)
                    .where(WatchlistModel.organization_id == organization_id)
                )
            ).scalar_one()
        )
        await self._billing.require_within_limit(
            organization_id, metric="max_watchlists", current=count
        )
        exists = (
            await self._session.execute(
                select(func.count())
                .select_from(WatchlistModel)
                .where(
                    WatchlistModel.organization_id == organization_id,
                    WatchlistModel.name == cleaned,
                )
            )
        ).scalar_one()
        if int(exists) > 0:
            raise ConflictError("a watchlist with this name already exists")
        model = WatchlistModel(
            organization_id=organization_id,
            name=cleaned,
            created_by=created_by,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self._session.add(model)
        await self._session.flush()
        return await self._to_dto(model)

    async def rename(
        self, organization_id: TenantId, watchlist_id: UUID, *, name: str
    ) -> WatchlistDTO:
        model = await self._get_model(organization_id, watchlist_id)
        cleaned = name.strip()
        if not cleaned:
            raise ValidationFailed("watchlist name is required")
        model.name = cleaned
        model.updated_at = utc_now()
        await self._session.flush()
        return await self._to_dto(model)

    async def remove(self, organization_id: TenantId, watchlist_id: UUID) -> None:
        model = await self._get_model(organization_id, watchlist_id)
        await self._session.delete(model)
        await self._session.flush()

    async def add_item(
        self, organization_id: TenantId, watchlist_id: UUID, *, instrument_id: UUID
    ) -> WatchlistDTO:
        model = await self._get_model(organization_id, watchlist_id)
        instrument = await self._instruments.get(instrument_id)
        if instrument is None:
            raise NotFoundError("instrument not found")
        existing = (
            await self._session.execute(
                select(func.count())
                .select_from(WatchlistItemModel)
                .where(
                    WatchlistItemModel.watchlist_id == watchlist_id,
                    WatchlistItemModel.instrument_id == instrument_id,
                )
            )
        ).scalar_one()
        if int(existing) > 0:
            raise ConflictError("instrument is already in this watchlist")
        max_sort = (
            await self._session.execute(
                select(func.coalesce(func.max(WatchlistItemModel.sort_order), 0)).where(
                    WatchlistItemModel.watchlist_id == watchlist_id
                )
            )
        ).scalar_one()
        self._session.add(
            WatchlistItemModel(
                watchlist_id=watchlist_id,
                instrument_id=instrument_id,
                sort_order=int(max_sort) + 1,
                added_at=utc_now(),
            )
        )
        model.updated_at = utc_now()
        await self._session.flush()
        return await self._to_dto(model)

    async def remove_item(
        self, organization_id: TenantId, watchlist_id: UUID, *, item_id: UUID
    ) -> WatchlistDTO:
        model = await self._get_model(organization_id, watchlist_id)
        await self._session.execute(
            delete(WatchlistItemModel).where(
                WatchlistItemModel.id == item_id,
                WatchlistItemModel.watchlist_id == watchlist_id,
            )
        )
        model.updated_at = utc_now()
        await self._session.flush()
        return await self._to_dto(model)

    async def _get_model(self, organization_id: TenantId, watchlist_id: UUID) -> WatchlistModel:
        model = await self._session.get(WatchlistModel, watchlist_id)
        if model is None or model.organization_id != organization_id:
            raise NotFoundError("watchlist not found")
        return model

    async def _to_dto(self, model: WatchlistModel) -> WatchlistDTO:
        items = (
            (
                await self._session.execute(
                    select(WatchlistItemModel)
                    .where(WatchlistItemModel.watchlist_id == model.id)
                    .order_by(WatchlistItemModel.sort_order)
                )
            )
            .scalars()
            .all()
        )
        summaries = await self._instruments.get_map([i.instrument_id for i in items])
        return WatchlistDTO(
            id=model.id,
            name=model.name,
            created_at=model.created_at,
            items=[
                WatchlistItemDTO(
                    id=i.id,
                    instrument_id=i.instrument_id,
                    symbol=summaries[i.instrument_id].symbol
                    if i.instrument_id in summaries
                    else "?",
                    name=summaries[i.instrument_id].name if i.instrument_id in summaries else "",
                    sort_order=i.sort_order,
                )
                for i in items
            ],
        )
