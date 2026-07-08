"""Feature-flag application service: storage, caching, and evaluation.

Flags and their scoped overrides live in Postgres so they are configurable at
runtime with no deployment. The whole (small) flag set is cached in Redis for a
short TTL and invalidated on every write, so hot-path checks avoid the database
without going stale for long. Evaluation itself is delegated to the pure domain.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.feature_flags.domain.flags import (
    EvaluationContext,
    FlagDefinition,
    FlagOverride,
    ScopeType,
    evaluate,
)
from algo_platform.modules.feature_flags.infrastructure.models import (
    FeatureFlagModel,
    FeatureFlagOverrideModel,
)
from algo_platform.shared.infrastructure.redis_gateway import RedisGateway

_CACHE_KEY = "ff:snapshot"


@dataclass(frozen=True, slots=True)
class FeatureFlagDTO:
    key: str
    description: str
    enabled: bool
    kill_switch: bool
    rollout_percentage: int


@dataclass(frozen=True, slots=True)
class FlagOverrideDTO:
    scope_type: str
    scope_id: str
    enabled: bool


Snapshot = dict[str, tuple[FlagDefinition, list[FlagOverride]]]


class FeatureFlagService:
    def __init__(
        self,
        session: AsyncSession,
        redis: RedisGateway | None = None,
        *,
        cache_ttl_seconds: int = 30,
    ) -> None:
        self._session = session
        self._redis = redis
        self._ttl = cache_ttl_seconds

    # -- evaluation --------------------------------------------------------
    async def is_enabled(self, key: str, context: EvaluationContext) -> bool:
        snapshot = await self._snapshot()
        entry = snapshot.get(key)
        if entry is None:
            return False  # unknown flags are off
        definition, overrides = entry
        return evaluate(definition, overrides, context)

    async def evaluate_all(self, context: EvaluationContext) -> dict[str, bool]:
        snapshot = await self._snapshot()
        return {
            key: evaluate(definition, overrides, context)
            for key, (definition, overrides) in snapshot.items()
        }

    # -- administration ----------------------------------------------------
    async def list_flags(self) -> list[FeatureFlagDTO]:
        rows = (
            await self._session.execute(select(FeatureFlagModel).order_by(FeatureFlagModel.key))
        ).scalars().all()
        return [
            FeatureFlagDTO(
                key=r.key,
                description=r.description,
                enabled=r.enabled,
                kill_switch=r.kill_switch,
                rollout_percentage=r.rollout_percentage,
            )
            for r in rows
        ]

    async def list_overrides(self, key: str) -> list[FlagOverrideDTO]:
        rows = (
            await self._session.execute(
                select(FeatureFlagOverrideModel).where(
                    FeatureFlagOverrideModel.flag_key == key
                )
            )
        ).scalars().all()
        return [
            FlagOverrideDTO(scope_type=r.scope_type, scope_id=r.scope_id, enabled=r.enabled)
            for r in rows
        ]

    async def upsert_flag(
        self,
        *,
        key: str,
        description: str = "",
        enabled: bool = False,
        kill_switch: bool = False,
        rollout_percentage: int = 100,
    ) -> None:
        stmt = pg_insert(FeatureFlagModel).values(
            key=key,
            description=description,
            enabled=enabled,
            kill_switch=kill_switch,
            rollout_percentage=rollout_percentage,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[FeatureFlagModel.key],
            set_={
                "description": stmt.excluded.description,
                "enabled": stmt.excluded.enabled,
                "kill_switch": stmt.excluded.kill_switch,
                "rollout_percentage": stmt.excluded.rollout_percentage,
            },
        )
        await self._session.execute(stmt)
        await self._invalidate()

    async def set_override(
        self, *, flag_key: str, scope_type: ScopeType, scope_id: str, enabled: bool
    ) -> None:
        stmt = pg_insert(FeatureFlagOverrideModel).values(
            flag_key=flag_key,
            scope_type=scope_type.value,
            scope_id=scope_id,
            enabled=enabled,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_feature_flag_overrides_scope",
            set_={"enabled": stmt.excluded.enabled},
        )
        await self._session.execute(stmt)
        await self._invalidate()

    async def clear_override(
        self, *, flag_key: str, scope_type: ScopeType, scope_id: str
    ) -> None:
        await self._session.execute(
            delete(FeatureFlagOverrideModel).where(
                FeatureFlagOverrideModel.flag_key == flag_key,
                FeatureFlagOverrideModel.scope_type == scope_type.value,
                FeatureFlagOverrideModel.scope_id == scope_id,
            )
        )
        await self._invalidate()

    # -- snapshot + cache --------------------------------------------------
    async def _snapshot(self) -> Snapshot:
        cached = await self._read_cache()
        if cached is not None:
            return cached
        snapshot = await self._load_from_db()
        await self._write_cache(snapshot)
        return snapshot

    async def _load_from_db(self) -> Snapshot:
        flags = (await self._session.execute(select(FeatureFlagModel))).scalars().all()
        overrides = (
            await self._session.execute(select(FeatureFlagOverrideModel))
        ).scalars().all()
        by_key: Snapshot = {
            f.key: (
                FlagDefinition(
                    key=f.key,
                    enabled=f.enabled,
                    kill_switch=f.kill_switch,
                    rollout_percentage=f.rollout_percentage,
                ),
                [],
            )
            for f in flags
        }
        for override in overrides:
            entry = by_key.get(override.flag_key)
            if entry is not None:
                entry[1].append(
                    FlagOverride(
                        scope_type=ScopeType(override.scope_type),
                        scope_id=override.scope_id,
                        enabled=override.enabled,
                    )
                )
        return by_key

    async def _read_cache(self) -> Snapshot | None:
        if self._redis is None:
            return None
        raw = await self._redis.get_json(_CACHE_KEY)
        if raw is None:
            return None
        return _decode_snapshot(raw)

    async def _write_cache(self, snapshot: Snapshot) -> None:
        if self._redis is None:
            return
        await self._redis.set_json(_CACHE_KEY, _encode_snapshot(snapshot), ttl_seconds=self._ttl)

    async def _invalidate(self) -> None:
        if self._redis is not None:
            await self._redis.delete(_CACHE_KEY)


def _encode_snapshot(snapshot: Snapshot) -> dict[str, object]:
    return {
        key: {
            "enabled": definition.enabled,
            "kill_switch": definition.kill_switch,
            "rollout_percentage": definition.rollout_percentage,
            "overrides": [
                {"scope_type": o.scope_type.value, "scope_id": o.scope_id, "enabled": o.enabled}
                for o in overrides
            ],
        }
        for key, (definition, overrides) in snapshot.items()
    }


def _decode_snapshot(raw: dict[str, object]) -> Snapshot:
    snapshot: Snapshot = {}
    for key, value in raw.items():
        data = value if isinstance(value, dict) else {}
        definition = FlagDefinition(
            key=key,
            enabled=bool(data.get("enabled", False)),
            kill_switch=bool(data.get("kill_switch", False)),
            rollout_percentage=int(data.get("rollout_percentage", 100)),
        )
        overrides = [
            FlagOverride(
                scope_type=ScopeType(o["scope_type"]),
                scope_id=str(o["scope_id"]),
                enabled=bool(o["enabled"]),
            )
            for o in data.get("overrides", [])
        ]
        snapshot[key] = (definition, overrides)
    return snapshot
