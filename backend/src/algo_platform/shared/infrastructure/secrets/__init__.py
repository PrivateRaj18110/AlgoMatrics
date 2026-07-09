"""Secrets management: pluggable providers with a safe .env fallback.

The platform resolves sensitive material (JWT keys, broker KEK, payment
provider secrets) through a :class:`SecretsProvider`. The default provider is
env/.env, preserving existing behaviour exactly; AWS Secrets Manager and an
encrypted local-development store are opt-in backends selected by
``SECRETS_BACKEND``. A :class:`SecretsResolver` layers each provider over the
original settings loaders so a missing managed secret always falls back to the
current configuration rather than failing.
"""

from __future__ import annotations

from algo_platform.shared.infrastructure.secrets.provider import (
    SecretsProvider,
    SecretsResolver,
    build_secrets_provider,
)

__all__ = ["SecretsProvider", "SecretsResolver", "build_secrets_provider"]
