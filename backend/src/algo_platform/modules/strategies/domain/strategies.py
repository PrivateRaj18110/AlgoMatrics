"""Strategy aggregates: definitions, immutable versions, runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from algo_platform.shared.domain.errors import (
    ConflictError,
    InvariantViolation,
    ValidationFailed,
)
from algo_platform.shared.domain.types import (
    AccountId,
    StrategyRunId,
    TenantId,
    UserId,
    utc_now,
)


class StrategyStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class VersionSource(StrEnum):
    BUILTIN = "builtin"
    UPLOADED = "uploaded"


class RunState(StrEnum):
    PENDING = "pending"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


ACTIVE_RUN_STATES = frozenset(
    {RunState.PENDING, RunState.STARTING, RunState.RUNNING, RunState.PAUSED, RunState.STOPPING}
)


@dataclass(slots=True)
class Strategy:
    id: UUID
    organization_id: TenantId
    name: str
    description: str
    tags: list[str]
    status: StrategyStatus = StrategyStatus.DRAFT
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
        name: str,
        description: str,
        tags: list[str],
        created_by: UserId,
    ) -> Strategy:
        cleaned = name.strip()
        if not cleaned:
            raise ValidationFailed("strategy name is required")
        return cls(
            id=uuid4(),
            organization_id=organization_id,
            name=cleaned,
            description=description.strip(),
            tags=[t.strip().lower() for t in tags if t.strip()][:10],
            created_by=created_by,
        )

    def update_details(
        self, *, name: str | None, description: str | None, tags: list[str] | None
    ) -> None:
        if name is not None:
            cleaned = name.strip()
            if not cleaned:
                raise ValidationFailed("strategy name cannot be empty")
            self.name = cleaned
        if description is not None:
            self.description = description.strip()
        if tags is not None:
            self.tags = [t.strip().lower() for t in tags if t.strip()][:10]
        self.updated_at = utc_now()

    def activate(self) -> None:
        if self.status is StrategyStatus.ARCHIVED:
            raise ConflictError("archived strategies cannot be activated")
        self.status = StrategyStatus.ACTIVE
        self.updated_at = utc_now()

    def archive(self) -> None:
        self.status = StrategyStatus.ARCHIVED
        self.updated_at = utc_now()


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    name: str
    type: str  # "int" | "float" | "str" | "bool"
    default: Any
    minimum: float | None = None
    maximum: float | None = None
    description: str = ""

    def validate_value(self, value: Any) -> Any:
        if self.type == "int":
            try:
                coerced: Any = int(value)
            except (TypeError, ValueError) as error:
                raise ValidationFailed(f"parameter '{self.name}' must be an integer") from error
        elif self.type == "float":
            try:
                coerced = float(value)
            except (TypeError, ValueError) as error:
                raise ValidationFailed(f"parameter '{self.name}' must be a number") from error
        elif self.type == "bool":
            coerced = bool(value)
        else:
            coerced = str(value)
        if self.minimum is not None and isinstance(coerced, int | float) and coerced < self.minimum:
            raise ValidationFailed(f"parameter '{self.name}' must be >= {self.minimum}")
        if self.maximum is not None and isinstance(coerced, int | float) and coerced > self.maximum:
            raise ValidationFailed(f"parameter '{self.name}' must be <= {self.maximum}")
        return coerced


@dataclass(slots=True)
class StrategyVersion:
    id: UUID
    strategy_id: UUID
    organization_id: TenantId
    version: int
    source: VersionSource
    entry_point: str
    artifact_path: str | None
    checksum: str
    manifest: dict[str, Any]
    approved_for_live: bool = False
    created_by: UserId | None = None
    created_at: datetime = field(default_factory=utc_now)

    def parameter_specs(self) -> list[ParameterSpec]:
        specs: list[ParameterSpec] = []
        for raw in self.manifest.get("parameters", []):
            specs.append(
                ParameterSpec(
                    name=str(raw["name"]),
                    type=str(raw.get("type", "float")),
                    default=raw.get("default"),
                    minimum=float(raw["min"]) if raw.get("min") is not None else None,
                    maximum=float(raw["max"]) if raw.get("max") is not None else None,
                    description=str(raw.get("description", "")),
                )
            )
        return specs

    def resolve_parameters(self, overrides: dict[str, Any]) -> dict[str, Any]:
        specs = {s.name: s for s in self.parameter_specs()}
        unknown = set(overrides) - set(specs)
        if unknown:
            raise ValidationFailed(f"unknown parameters: {', '.join(sorted(unknown))}")
        resolved: dict[str, Any] = {}
        for name, spec in specs.items():
            value = overrides.get(name, spec.default)
            resolved[name] = spec.validate_value(value)
        return resolved


@dataclass(slots=True)
class StrategyRun:
    id: StrategyRunId
    organization_id: TenantId
    strategy_id: UUID
    strategy_version_id: UUID
    account_id: AccountId
    mode: str  # "paper" | "live"
    state: RunState
    parameters: dict[str, Any]
    instrument_ids: list[UUID]
    timeframe: str
    created_by: UserId | None = None
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    error: str | None = None
    stats: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    version: int = 1

    @classmethod
    def create(
        cls,
        *,
        organization_id: TenantId,
        strategy_id: UUID,
        strategy_version_id: UUID,
        account_id: AccountId,
        mode: str,
        parameters: dict[str, Any],
        instrument_ids: list[UUID],
        timeframe: str,
        created_by: UserId,
    ) -> StrategyRun:
        if mode not in {"paper", "live"}:
            raise ValidationFailed("mode must be paper or live")
        if not instrument_ids:
            raise ValidationFailed("select at least one instrument")
        if len(instrument_ids) > 20:
            raise ValidationFailed("a run may subscribe to at most 20 instruments")
        if timeframe not in {"tick", "1m", "5m", "15m", "1h"}:
            raise ValidationFailed("timeframe must be one of tick, 1m, 5m, 15m, 1h")
        return cls(
            id=StrategyRunId(uuid4()),
            organization_id=organization_id,
            strategy_id=strategy_id,
            strategy_version_id=strategy_version_id,
            account_id=account_id,
            mode=mode,
            state=RunState.PENDING,
            parameters=parameters,
            instrument_ids=list(instrument_ids),
            timeframe=timeframe,
            created_by=created_by,
        )

    @property
    def is_active(self) -> bool:
        return self.state in ACTIVE_RUN_STATES

    def _transition(self, allowed: frozenset[RunState], new_state: RunState) -> None:
        if self.state not in allowed:
            raise InvariantViolation(
                f"cannot move run from {self.state.value} to {new_state.value}"
            )
        self.state = new_state
        self.updated_at = utc_now()
        self.version += 1

    def request_start(self) -> None:
        self._transition(
            frozenset({RunState.PENDING, RunState.STOPPED, RunState.FAILED, RunState.PAUSED}),
            RunState.STARTING,
        )
        self.error = None

    def mark_running(self) -> None:
        self._transition(frozenset({RunState.STARTING, RunState.PAUSED}), RunState.RUNNING)
        if self.started_at is None:
            self.started_at = utc_now()
        self.last_heartbeat_at = utc_now()

    def pause(self) -> None:
        self._transition(frozenset({RunState.RUNNING}), RunState.PAUSED)

    def request_stop(self) -> None:
        self._transition(
            frozenset({RunState.PENDING, RunState.STARTING, RunState.RUNNING, RunState.PAUSED}),
            RunState.STOPPING,
        )

    def mark_stopped(self) -> None:
        self._transition(
            frozenset({RunState.STOPPING, RunState.RUNNING, RunState.PAUSED, RunState.STARTING}),
            RunState.STOPPED,
        )
        self.stopped_at = utc_now()

    def mark_failed(self, error: str) -> None:
        self.state = RunState.FAILED
        self.error = error[:500]
        self.stopped_at = utc_now()
        self.updated_at = utc_now()
        self.version += 1

    def heartbeat(self, stats: dict[str, Any] | None = None) -> None:
        self.last_heartbeat_at = utc_now()
        if stats:
            merged = dict(self.stats)
            merged.update(stats)
            self.stats = merged
        self.updated_at = utc_now()
