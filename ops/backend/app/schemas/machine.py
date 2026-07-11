"""Machine (host) schemas."""

from pydantic import BaseModel

from app.schemas.common import Status


class Machine(BaseModel):
    """A monitored host: VPS, cloud instance or workstation."""

    id: str
    name: str
    location: str
    provider: str
    status: Status
    cpu: float
    ram: float
    disk: float
    temperatureC: float | None
    internetMs: float
    brokerPingMs: float
    pythonStatus: Status
    uptimeSec: int
    lastHeartbeat: str
    strategyCount: int
