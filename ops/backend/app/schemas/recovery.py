"""Offline/recovery dashboard schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.common import Status

RecoveryState = Literal["online", "degraded", "offline", "recovering", "unknown"]


class RecoveryMachine(BaseModel):
    machineId: str
    machine: str
    status: Status
    recoveryState: RecoveryState
    lastHeartbeat: str | None = None
    heartbeatAgeSec: int | None = None
    offlineDurationSec: int | None = None
    queueDepth: int | None = None
    oldestPendingAgeSec: int | None = None
    transportState: str | None = None
    currentSessionId: str | None = None
    tradingProcessState: str | None = None
    lastEodSync: str | None = None
    lastEodStatus: str | None = None
    eodBacklog: int
    eventsRecovered: int
    acceptedEvents: int
    duplicateEvents: int
    failedEvents: int
    missingEvents: int
    gapCount: int
    lastGapAt: str | None = None
    lastRecovery: str | None = None
    warnings: list[str] = Field(default_factory=list)


class RecoverySummary(BaseModel):
    generatedAt: str
    totalMachines: int
    online: int
    degraded: int
    offline: int
    unknown: int
    recovering: int
    totalQueueDepth: int
    totalEodBacklog: int
    totalMissingEvents: int
    machines: list[RecoveryMachine]
