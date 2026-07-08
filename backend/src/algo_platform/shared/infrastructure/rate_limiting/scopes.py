"""Rate-limit scope keys: tenant, user, API key, IP, broker, route.

Pure helpers that turn a request's identities into the set of Redis keys that
must each pass. A request is limited if *any* applicable scope is exceeded.
"""

from __future__ import annotations

from enum import StrEnum


class Scope(StrEnum):
    TENANT = "tenant"
    USER = "user"
    API_KEY = "api_key"
    IP = "ip"
    BROKER = "broker"
    ROUTE = "route"


def scope_keys(name: str, subjects: dict[Scope, str | None]) -> list[tuple[Scope, str]]:
    """Build ``(scope, redis_key)`` pairs for every subject that is present.

    ``name`` namespaces the limiter (e.g. the route name) so different limited
    operations do not share a budget for the same subject.
    """
    keys: list[tuple[Scope, str]] = []
    for scope, subject in subjects.items():
        if subject:
            keys.append((scope, f"rl:{name}:{scope.value}:{subject}"))
    return keys
