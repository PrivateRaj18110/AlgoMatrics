"""Agent authentication for the telemetry write path.

Every ``/api/agent/*`` and ``/api/ingest/*`` route depends on
:func:`require_agent_token`. The Raj Local Agent has always sent
``X-Raj-Agent-Token`` (``raj_monitor/security.py::backend_headers``); until this
module existed the server simply ignored it.

**Fail closed, always.** ``raj_monitor/security.py::tokens_match`` returns True
when no token is configured — correct for the SDK↔agent hop, which never leaves
localhost, and wrong for a network hop. That behaviour is deliberately *not*
mirrored here: an unconfigured server rejects every request rather than
accepting every request.

Nothing in this module logs, echoes, or returns a credential. Every rejection is
the same opaque 401 regardless of cause, so the response cannot be used to probe
which machine names or tokens exist.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header, HTTPException, status

from app.core.config import get_settings
from app.core.security import hash_token

# One message for every failure mode. Distinguishing "missing" from "invalid"
# from "unconfigured" would tell an unauthenticated caller how far they got.
_UNAUTHORIZED = "agent authentication required"


@dataclass(frozen=True, slots=True)
class AgentPrincipal:
    """The authenticated caller behind an ingestion request.

    ``machine`` is the scope the credential is bound to, or ``None`` for a
    fleet-wide token. ``agent_id`` is advisory identity from the request header
    — it is *not* a credential and must never be used for an authorization
    decision on its own.
    """

    machine: str | None
    agent_id: str | None

    @property
    def is_fleet_scoped(self) -> bool:
        return self.machine is None

    def authorizes_machine(self, machine: str | None) -> bool:
        """True when this principal may write telemetry for ``machine``."""
        if self.is_fleet_scoped:
            return True
        if not machine:
            # A machine-scoped credential must not write unattributed telemetry.
            return False
        return machine.strip().lower() == (self.machine or "").strip().lower()


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=_UNAUTHORIZED,
        headers={"WWW-Authenticate": "Token"},
    )


async def require_agent_token(
    x_raj_agent_token: str | None = Header(default=None, alias="X-Raj-Agent-Token"),
    x_raj_agent_id: str | None = Header(default=None, alias="X-Raj-Agent-Id"),
) -> AgentPrincipal:
    """Authenticate an agent request, or raise 401.

    Resolution order:

    1. No credential configured on the server -> 401 (fail closed).
    2. No credential presented by the caller  -> 401.
    3. Presented credential's digest is not in the index -> 401.
    4. Otherwise -> :class:`AgentPrincipal` carrying the token's machine scope.

    The lookup hashes the presented token and compares fixed-width digests, so
    comparison time does not vary with how much of a real token was guessed.
    """
    settings = get_settings()
    index = settings.agent_token_index
    if not index:  # rule 1 — unconfigured means closed, never open
        raise _unauthorized()

    presented = (x_raj_agent_token or "").strip()
    if not presented:  # rule 2
        raise _unauthorized()

    scope = index.get(hash_token(presented), ...)
    if scope is ...:  # rule 3 — sentinel, because a valid scope may be None
        raise _unauthorized()

    return AgentPrincipal(machine=scope, agent_id=(x_raj_agent_id or "").strip() or None)


def enforce_machine_scope(principal: AgentPrincipal, machine: str | None) -> None:
    """Reject a payload that writes telemetry for a machine outside the scope.

    Separated from the header check because the machine lives in the request
    *body*, which FastAPI has not parsed when the dependency runs. Routers call
    this immediately after their payload is bound.
    """
    if not principal.authorizes_machine(machine):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="credential is not authorized for this machine",
        )
