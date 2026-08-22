"""Authentication helpers.

Two trust boundaries exist:

1. **SDK <-> Local Agent** — a *shared local token*. Because the agent only binds
   to localhost, this token mainly stops other local users/processes from
   injecting telemetry. Compared in constant time.
2. **Agent <-> Backend** — a *backend token* sent over HTTPS in a header.

This module never logs token values.
"""

from __future__ import annotations

import hmac
import secrets

from . import constants


def generate_token(nbytes: int = 32) -> str:
    """Return a fresh URL-safe random token (for bootstrapping config)."""
    return secrets.token_urlsafe(nbytes)


def tokens_match(expected: str | None, provided: str | None) -> bool:
    """Constant-time comparison.

    If no token is configured (``expected`` is falsy), auth is disabled and any
    request is accepted — convenient for local development, but the install docs
    strongly recommend setting tokens in production.
    """
    if not expected:
        return True
    if not provided:
        return False
    return hmac.compare_digest(str(expected), str(provided))


def local_headers(local_token: str | None) -> dict[str, str]:
    """Headers the SDK sends to the Local Agent."""
    # The SDK opens a fresh connection per envelope and closes it right after, so
    # declare ``Connection: close`` to keep both ends in agreement. Without it the
    # default HTTP/1.1 keep-alive expectation races the client close on Windows
    # and resets the socket (WinError 10053/10054), dropping rapid posts.
    headers = {"Content-Type": "application/json", "Connection": "close"}
    if local_token:
        headers[constants.LOCAL_TOKEN_HEADER] = local_token
    return headers


def backend_headers(backend_token: str | None, agent_id: str | None = None) -> dict[str, str]:
    """Headers the agent sends to the FastAPI backend."""
    headers = {"Content-Type": "application/json"}
    if backend_token:
        headers[constants.BACKEND_TOKEN_HEADER] = backend_token
    if agent_id:
        headers[constants.AGENT_ID_HEADER] = agent_id
    return headers
