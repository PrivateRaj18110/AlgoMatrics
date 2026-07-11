"""System event schemas."""

from typing import Literal

from pydantic import BaseModel

from app.schemas.common import Severity

EventCategory = Literal[
    "trade", "strategy", "machine", "broker", "system", "database", "risk"
]


class SystemEvent(BaseModel):
    """A single line in the live event terminal."""

    id: str
    time: str
    category: EventCategory
    severity: Severity
    source: str
    message: str
