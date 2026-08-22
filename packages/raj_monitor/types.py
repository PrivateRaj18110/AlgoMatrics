"""Typed data structures shared across the platform.

These dataclasses describe the wire envelopes that flow Strategy -> SDK -> Agent
-> Backend. They are intentionally plain (``dataclass`` + ``asdict``) so they
serialise to JSON with no third-party dependency, keeping the SDK lightweight.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def now_iso() -> str:
    """Current UTC time as an ISO-8601 string (the platform's timestamp format)."""
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str = "evt") -> str:
    """Short, sortable-ish unique id for an item."""
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@dataclass(slots=True)
class Identity:
    """Who is reporting — attached to every envelope."""

    strategy: str
    machine: str
    account: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass(slots=True)
class Envelope:
    """A single unit of telemetry handed from the SDK to the agent.

    ``kind`` is the discriminator (see :mod:`raj_monitor.constants`); ``data``
    is the kind-specific body. The agent persists these verbatim and later
    forwards them to the backend in batches.
    """

    kind: str
    data: dict[str, Any]
    strategy: str
    machine: str
    account: str | None = None
    ts: str = field(default_factory=now_iso)
    id: str = field(default_factory=lambda: new_id("env"))
    protocol: int = 1

    def as_dict(self) -> dict[str, Any]:
        out = {
            "id": self.id,
            "kind": self.kind,
            "ts": self.ts,
            "strategy": self.strategy,
            "machine": self.machine,
            "protocol": self.protocol,
            "data": self.data,
        }
        if self.account is not None:
            out["account"] = self.account
        return out

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Envelope":
        return cls(
            kind=raw["kind"],
            data=raw.get("data", {}),
            strategy=raw.get("strategy", "unknown"),
            machine=raw.get("machine", "unknown"),
            account=raw.get("account"),
            ts=raw.get("ts", now_iso()),
            id=raw.get("id", new_id("env")),
            protocol=raw.get("protocol", 1),
        )


@dataclass(slots=True)
class QueuedItem:
    """A row read back from the persistent queue."""

    rowid: int
    envelope: Envelope
    attempts: int
    created_at: float = field(default_factory=time.time)
