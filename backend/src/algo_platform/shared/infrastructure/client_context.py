"""Who is on the other end of the current request.

Set once per request by the request-context middleware, read wherever evidence
is recorded (the audit log), so no call site has to thread the client's address
and browser through by hand. Outside a request (workers, scripts) it is empty.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClientInfo:
    ip_address: str | None
    user_agent: str | None


_current: ContextVar[ClientInfo | None] = ContextVar("request_client", default=None)


def set_client(info: ClientInfo | None) -> None:
    _current.set(info)


def current_client() -> ClientInfo | None:
    return _current.get()
