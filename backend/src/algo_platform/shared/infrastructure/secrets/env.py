"""Environment-variable secrets backend (the default, .env-compatible fallback).

Looks up an optional per-secret override under ``<PREFIX><NAME>`` (e.g.
``ALGO_SECRET_JWT_PRIVATE_KEY``). When no override is set it returns ``None`` so
the resolver falls back to the existing settings/.env value — meaning selecting
this backend changes nothing unless an override is explicitly provided.
"""

from __future__ import annotations

import os


class EnvSecretsProvider:
    def __init__(self, *, prefix: str = "ALGO_SECRET_") -> None:
        self._prefix = prefix

    def get(self, name: str) -> str | None:
        raw = os.environ.get(f"{self._prefix}{name.upper()}")
        if raw is None:
            return None
        # A blank override is treated as "unset" so an empty env var cannot
        # accidentally wipe out a real fallback value.
        return raw if raw.strip() else None
