"""Keyed daily snapshots in ``market_snapshots`` (one row per kind per date)."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.market_insights.infrastructure.models import MarketSnapshotModel
from algo_platform.shared.domain.types import utc_now


class SqlSnapshotStore:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _row(self, kind: str, day: date) -> MarketSnapshotModel | None:
        stmt = select(MarketSnapshotModel).where(
            MarketSnapshotModel.kind == kind, MarketSnapshotModel.trade_date == day
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get(self, kind: str, day: date) -> Any | None:
        row = await self._row(kind, day)
        return None if row is None else row.payload

    async def latest(
        self, kind: str, *, on_or_before: date | None = None
    ) -> tuple[date, Any] | None:
        stmt = select(MarketSnapshotModel).where(MarketSnapshotModel.kind == kind)
        if on_or_before is not None:
            stmt = stmt.where(MarketSnapshotModel.trade_date <= on_or_before)
        stmt = stmt.order_by(MarketSnapshotModel.trade_date.desc()).limit(1)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return None if row is None else (row.trade_date, row.payload)

    async def history(self, kind: str, limit: int) -> list[tuple[date, Any]]:
        stmt = (
            select(MarketSnapshotModel)
            .where(MarketSnapshotModel.kind == kind)
            .order_by(MarketSnapshotModel.trade_date.desc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [(row.trade_date, row.payload) for row in rows]

    async def put(self, kind: str, day: date, payload: Any) -> None:
        row = await self._row(kind, day)
        if row is not None:
            row.payload = payload
            row.fetched_at = utc_now()
        else:
            self._session.add(
                MarketSnapshotModel(
                    kind=kind, trade_date=day, fetched_at=utc_now(), payload=payload
                )
            )
        await self._session.flush()

    async def commit(self) -> None:
        await self._session.commit()
