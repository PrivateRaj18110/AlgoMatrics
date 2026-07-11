"""Agent ingestion schemas — the contract the Raj Local Agent posts against.

These power the ``/api/agent/*`` endpoints. The agent (one per machine) is the
*only* client of these endpoints; trading strategies talk to the agent over
localhost, never to the backend directly.

The primary path is ``/api/agent/batch`` (a list of envelopes); the per-kind
endpoints exist for direct testing and finer-grained posting.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class AgentRegister(BaseModel):
    """`POST /api/agent/register` — announce an agent + its host."""

    agentId: str
    machine: str
    location: str | None = None
    provider: str | None = None
    sdkVersion: str | None = None
    python: str | None = None
    os: str | None = None


class AgentHeartbeat(BaseModel):
    """`POST /api/agent/heartbeat` — periodic liveness + host telemetry."""

    agentId: str
    machine: str
    python: str | None = None
    ts: str | None = None
    health: str | None = None
    cpu: float = 0.0
    ram: float = 0.0
    disk: float = 0.0
    internetMs: float = 0.0
    brokerPingMs: float = 0.0
    uptimeSec: int = 0
    mt5Running: bool = False
    strategyCount: int = 0


class Envelope(BaseModel):
    """One queued telemetry item produced by the SDK / agent."""

    id: str | None = None
    kind: str
    ts: str | None = None
    strategy: str = "unknown"
    machine: str = "unknown"
    account: str | None = None
    protocol: int = 1
    data: dict[str, Any] = Field(default_factory=dict)


class AgentBatch(BaseModel):
    """`POST /api/agent/batch` — the agent's main upload payload."""

    agentId: str
    machine: str
    count: int | None = None
    items: list[Envelope] = Field(default_factory=list)


class AgentAck(BaseModel):
    """Standard acknowledgement returned by every agent endpoint."""

    accepted: bool = True
    received: str
    kind: str
    processed: int = 1
    machineId: str | None = None
