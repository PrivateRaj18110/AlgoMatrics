"""System event schemas."""

from typing import Literal

from pydantic import BaseModel

from app.schemas.common import Severity

EventCategory = Literal[
    "trade", "strategy", "machine", "broker", "system", "database", "risk", "data"
]


class SystemEvent(BaseModel):
    """A single line in the live event terminal."""

    id: str
    time: str
    category: EventCategory
    severity: Severity
    source: str
    message: str
    machineId: str | None = None
    eventType: str | None = None
    strategy: str | None = None
    symbol: str | None = None
    sessionId: str | None = None
    sequenceId: int | None = None
    payloadSummary: str | None = None
    sourceEventType: str | None = None
