"""Alert schemas."""

from typing import Literal

from pydantic import BaseModel

from app.schemas.common import Severity

AlertType = Literal[
    "machine_offline",
    "high_cpu",
    "high_ram",
    "high_latency",
    "broker_offline",
    "strategy_crash",
]


class Alert(BaseModel):
    """An alert surfaced by the alert center."""

    id: str
    type: AlertType
    severity: Severity
    title: str
    message: str
    source: str
    time: str
    acknowledged: bool
