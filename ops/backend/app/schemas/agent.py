"""Agent ingestion schemas — the contract the Raj Local Agent posts against.

These power the ``/api/agent/*`` endpoints. The agent (one per machine) is the
*only* client of these endpoints; trading strategies talk to the agent over
localhost, never to the backend directly.

The primary path is ``/api/agent/batch`` (a list of envelopes); the per-kind
endpoints exist for direct testing and finer-grained posting.
"""

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


class AgentRegister(BaseModel):
    """`POST /api/agent/register` — announce an agent + its host."""

    agentId: str
    machine: str
    location: str | None = None
    provider: str | None = None
    sdkVersion: str | None = None
    python: str | None = None
    os: str | None = None
    hostname: str | None = None
    environment: str | None = None


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
    hostname: str | None = None
    environment: str | None = None
    queueDepth: int | None = None
    oldestPendingAgeSec: int | None = None
    transportState: str | None = None
    currentSessionId: str | None = None
    tradingProcessState: str | None = None
    lastEodSync: str | None = None
    lastEodStatus: str | None = None


class Envelope(BaseModel):
    """One queued telemetry item produced by the SDK / agent.

    The first block is the wire contract the shipped agent already sends
    (``raj_monitor/types.py::Envelope``) and is deliberately unchanged — renaming
    ``kind`` or ``data`` would force Google and AWS to be upgraded in lock-step,
    which is exactly the coupling this integration is designed to avoid.

    The second block is additive and optional. A current agent omits all three
    and is accepted unchanged; an upgraded agent gains ordering and session
    tracking without a protocol bump.
    """

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str | None = Field(default=None, validation_alias=AliasChoices("id", "event_id", "eventId"))
    kind: str | None = None
    ts: str | None = Field(default=None, validation_alias=AliasChoices("ts", "timestamp", "event_time"))
    strategy: str = "unknown"
    machine: str = "unknown"
    account: str | None = None
    protocol: int = 1
    data: dict[str, Any] = Field(default_factory=dict)

    # Google DataAgent / RajBridge fields. Additive — a shipped agent omits them.
    event_type: str | None = None
    source_event_type: str | None = None
    source: str | None = None
    agent_id: str | None = Field(default=None, validation_alias=AliasChoices("agent_id", "agentId"))

    # --- Additive (Phase 2). Optional for backward compatibility. ----------
    # Monotonic per (machine, agent). Enables gap detection; NOT a dedup key —
    # `id` remains the idempotency key.
    sequence_id: int | None = Field(
        default=None, description="Monotonic per-agent sequence number, if the agent assigns one."
    )
    # Version of THIS kind's payload, so a payload can evolve without changing
    # `protocol` (which versions the envelope itself).
    schema_version: int | None = Field(
        default=None, description="Payload schema version for this kind."
    )
    # Trading session key, e.g. "2026-08-09-NSE".
    session_id: str | None = Field(
        default=None, description="Trading session this envelope belongs to."
    )

    @model_validator(mode="before")
    @classmethod
    def _accept_data_agent_shape(cls, value: Any) -> Any:
        """Accept Google DataEventEnvelope keys without renaming the wire contract.

        ``kind`` / ``data`` stay the shipped-agent names. When they are absent,
        ``event_type`` / ``payload`` / ``event_id`` are copied in. When both
        ``kind`` and ``event_type`` are present they are kept independently so
        classification can prefer the Google type over a wrapper kind.
        """
        if not isinstance(value, dict):
            return value
        data = dict(value)
        payload = data.get("payload")
        health = data.get("health")
        if not data.get("data"):
            if isinstance(payload, dict):
                data["data"] = payload
            elif isinstance(health, dict):
                data["data"] = {"health": health, **health}
        if not data.get("id"):
            data["id"] = data.get("event_id") or data.get("eventId")
        if (not data.get("machine") or data.get("machine") == "unknown") and (
            data.get("machine_id") or data.get("machineId")
        ):
            data["machine"] = data.get("machine_id") or data.get("machineId")
        inner = data.get("data") if isinstance(data.get("data"), dict) else {}
        if not data.get("event_type"):
            data["event_type"] = (
                inner.get("event_type") or inner.get("eventType") or data.get("eventType")
            )
        if not data.get("source_event_type"):
            data["source_event_type"] = (
                inner.get("source_event_type")
                or inner.get("sourceEventType")
                or data.get("sourceEventType")
            )
        if not data.get("kind"):
            data["kind"] = data.get("event_type") or data.get("source_event_type")
        if not data.get("agent_id"):
            data["agent_id"] = data.get("agentId")
        return data

    @model_validator(mode="after")
    def _require_kind_or_event_type(self) -> "Envelope":
        if not (self.kind or self.event_type or self.source_event_type):
            raise ValueError("envelope requires kind, event_type, or source_event_type")
        return self


class AgentBatch(BaseModel):
    """`POST /api/agent/batch` — the agent's main upload payload."""

    agentId: str
    machine: str
    count: int | None = None
    items: list[Envelope] = Field(default_factory=list)
    # Optional depth of the agent's own outbound queue at send time.
    queueDepth: int | None = None


class EnvelopeOutcome(BaseModel):
    """Per-item result. One entry per envelope that was not plainly accepted."""

    id: str | None = None
    status: str  # "duplicate" | "rejected" | "failed"
    reason: str | None = None


class AgentAck(BaseModel):
    """Acknowledgement returned by every agent endpoint.

    The original five fields are preserved verbatim so the shipped agent, the
    existing dashboard and the existing contract test keep working.

    ``processed`` previously reported ``len(items)`` unconditionally — a batch
    containing malformed envelopes was still acknowledged as fully processed, so
    the agent deleted them from its durable queue and the data was gone with no
    record. It now reports only envelopes that were genuinely persisted, and the
    breakdown below makes every item's fate explicit.
    """

    accepted: bool = True
    received: str
    kind: str
    processed: int = 1
    machineId: str | None = None

    # --- Additive (Phase 2) ------------------------------------------------
    total: int | None = None
    duplicate: int | None = None
    rejected: int | None = None
    failed: int | None = None
    outcomes: list[EnvelopeOutcome] | None = None
    # Highest sequence_id recorded for this agent, and any gap seen in this
    # batch. Lets the agent (and a human) see loss without querying the DB.
    lastSequenceId: int | None = None
    sequenceGap: bool | None = None
