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
    agentId: str | None = None
    agentVersion: str | None = None
    hostname: str | None = None
    environment: str | None = None
    lastEvent: str | None = None
    lastTrade: str | None = None
    lastError: str | None = None
    lastSuccessfulUpload: str | None = None
    queueDepth: int | None = None
    oldestPendingAgeSec: int | None = None
    transportState: str | None = None
    currentSessionId: str | None = None
    tradingProcessState: str | None = None
    lastEodSync: str | None = None
    lastEodStatus: str | None = None
    recoveryState: str | None = None
    lastRecovery: str | None = None
    eventsRecovered: int | None = None
    eodBacklog: int | None = None
