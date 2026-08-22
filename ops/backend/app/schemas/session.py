"""Trading-session read models for the ops dashboard."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.eod import EodDatasetView
from app.schemas.event import SystemEvent


class SessionView(BaseModel):
    sessionId: str
    machineId: str
    machine: str
    status: Literal["open", "closed"]
    startedAt: str | None = None
    endedAt: str | None = None
    lastEventAt: str | None = None
    eventCount: int
    tradeCount: int


class SessionDetailView(BaseModel):
    session: SessionView
    recentEvents: list[SystemEvent] = Field(default_factory=list)
    eodDatasets: list[EodDatasetView] = Field(default_factory=list)
