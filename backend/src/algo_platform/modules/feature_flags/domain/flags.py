"""Feature-flag evaluation rules (pure, framework-free).

Evaluation precedence, most specific first:

1. **Kill switch** — an emergency off that overrides everything.
2. **User override** — explicit on/off for a single user.
3. **Tenant override** — explicit on/off for an organization.
4. **Environment override** — explicit on/off for an environment (local/prod...).
5. **Percentage rollout** — deterministic per-subject bucketing.
6. **Default** — the flag's ``enabled`` value.

Overrides are explicit decisions and therefore bypass percentage rollout. The
rollout only applies when no override matches and the flag is enabled.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class ScopeType(StrEnum):
    ENVIRONMENT = "environment"
    TENANT = "tenant"
    USER = "user"


@dataclass(frozen=True, slots=True)
class FlagDefinition:
    key: str
    enabled: bool
    kill_switch: bool
    rollout_percentage: int  # 0..100; 100 means "fully on when enabled"


@dataclass(frozen=True, slots=True)
class FlagOverride:
    scope_type: ScopeType
    scope_id: str
    enabled: bool


@dataclass(frozen=True, slots=True)
class EvaluationContext:
    environment: str
    organization_id: UUID | None = None
    user_id: UUID | None = None


def _bucket(key: str, subject: str) -> int:
    digest = hashlib.sha256(f"{key}:{subject}".encode()).hexdigest()
    return int(digest[:8], 16) % 100


def _match_override(
    overrides: list[FlagOverride], scope_type: ScopeType, scope_id: str | None
) -> bool | None:
    if scope_id is None:
        return None
    for override in overrides:
        if override.scope_type is scope_type and override.scope_id == scope_id:
            return override.enabled
    return None


def evaluate(
    definition: FlagDefinition,
    overrides: list[FlagOverride],
    context: EvaluationContext,
) -> bool:
    if definition.kill_switch:
        return False

    user_scope = str(context.user_id) if context.user_id else None
    tenant_scope = str(context.organization_id) if context.organization_id else None

    for scope_type, scope_id in (
        (ScopeType.USER, user_scope),
        (ScopeType.TENANT, tenant_scope),
        (ScopeType.ENVIRONMENT, context.environment),
    ):
        decided = _match_override(overrides, scope_type, scope_id)
        if decided is not None:
            return decided

    if not definition.enabled:
        return False
    if definition.rollout_percentage >= 100:
        return True
    if definition.rollout_percentage <= 0:
        return False
    # Prefer the most stable subject available so a user's experience is
    # consistent; fall back to organization, then to no rollout membership.
    subject = user_scope or tenant_scope
    if subject is None:
        return False
    return _bucket(definition.key, subject) < definition.rollout_percentage
