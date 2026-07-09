"""Secrets provider port, resolver, and backend factory."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import structlog

if TYPE_CHECKING:
    from algo_platform.config import Settings

logger = structlog.get_logger("secrets")

# Canonical logical secret names. Backends key their stored values by these.
JWT_PRIVATE_KEY = "jwt_private_key"
JWT_PUBLIC_KEY = "jwt_public_key"
BROKER_CREDENTIAL_KEK = "broker_credential_kek"
RAZORPAY_KEY_SECRET = "razorpay_key_secret"  # noqa: S105 - logical secret name, not a value
RAZORPAY_WEBHOOK_SECRET = "razorpay_webhook_secret"  # noqa: S105 - logical secret name, not a value
STRIPE_SECRET_KEY = "stripe_secret_key"  # noqa: S105 - logical secret name, not a value
STRIPE_WEBHOOK_SECRET = "stripe_webhook_secret"  # noqa: S105 - logical secret name, not a value


@runtime_checkable
class SecretsProvider(Protocol):
    """Resolves a logical secret name to its value, or ``None`` if unmanaged.

    Returning ``None`` (rather than raising) signals "not provided by this
    backend", which the resolver treats as an instruction to fall back to the
    existing settings/.env value.
    """

    def get(self, name: str) -> str | None: ...


class SecretsResolver:
    """Layers a :class:`SecretsProvider` over the original settings loaders.

    Every accessor consults the managed provider first and falls back to the
    exact behaviour that existed before secrets management, so enabling a
    backend can never regress a working deployment.
    """

    def __init__(self, provider: SecretsProvider, settings: Settings) -> None:
        self._provider = provider
        self._settings = settings

    def _required(self, name: str, fallback: Callable[[], str]) -> str:
        managed = self._safe_get(name)
        if managed is not None:
            return managed
        return fallback()

    def _optional(self, name: str, fallback_value: str | None) -> str | None:
        managed = self._safe_get(name)
        if managed is not None:
            return managed
        return fallback_value

    def _safe_get(self, name: str) -> str | None:
        try:
            return self._provider.get(name)
        except Exception:
            # A backend outage must not take down startup when a local fallback
            # exists; log without the value and defer to the fallback.
            logger.warning("secrets.provider_lookup_failed", secret=name)
            return None

    # -- required material -------------------------------------------------
    def jwt_private_key(self) -> str:
        return self._required(JWT_PRIVATE_KEY, self._settings.load_jwt_private_key)

    def jwt_public_key(self) -> str:
        return self._required(JWT_PUBLIC_KEY, self._settings.load_jwt_public_key)

    def broker_credential_kek_b64(self) -> str:
        return self._required(BROKER_CREDENTIAL_KEK, self._settings.load_broker_kek_b64)

    # -- optional material -------------------------------------------------
    def razorpay_key_secret(self) -> str | None:
        return self._optional(RAZORPAY_KEY_SECRET, self._settings.razorpay_key_secret)

    def razorpay_webhook_secret(self) -> str | None:
        return self._optional(RAZORPAY_WEBHOOK_SECRET, self._settings.razorpay_webhook_secret)

    def stripe_secret_key(self) -> str | None:
        return self._optional(STRIPE_SECRET_KEY, self._settings.stripe_secret_key)

    def stripe_webhook_secret(self) -> str | None:
        return self._optional(STRIPE_WEBHOOK_SECRET, self._settings.stripe_webhook_secret)


def build_secrets_provider(settings: Settings) -> SecretsProvider:
    """Construct the configured secrets backend.

    Backends beyond ``env`` are imported lazily so their optional dependencies
    (e.g. boto3) are only required when actually selected.
    """
    backend = settings.secrets_backend
    if backend == "env":
        from algo_platform.shared.infrastructure.secrets.env import EnvSecretsProvider

        return EnvSecretsProvider(prefix=settings.secrets_env_prefix)
    if backend == "aws":
        from algo_platform.shared.infrastructure.secrets.aws import (
            AwsSecretsManagerProvider,
        )

        return AwsSecretsManagerProvider(
            secret_id=settings.aws_secrets_id,
            region_name=settings.aws_region or None,
            cache_ttl_seconds=settings.secrets_cache_ttl_seconds,
        )
    if backend == "encrypted":
        from algo_platform.shared.infrastructure.secrets.encrypted import (
            EncryptedFileSecretsProvider,
        )

        return EncryptedFileSecretsProvider(
            path=settings.secrets_encrypted_file,
            key=settings.load_secrets_encryption_key(),
        )
    raise ValueError(f"unknown secrets backend: {backend!r}")
