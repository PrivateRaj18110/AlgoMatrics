"""Unit tests for secrets management (Phase 2, slice A)."""

from __future__ import annotations

import pytest

from algo_platform.config import Settings
from algo_platform.shared.infrastructure.secrets.env import EnvSecretsProvider
from algo_platform.shared.infrastructure.secrets.provider import (
    SecretsResolver,
    build_secrets_provider,
)
from algo_platform.shared.infrastructure.telemetry import _redact_secrets


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url": "postgresql+asyncpg://u:p@localhost/db",
        "redis_url": "redis://localhost:6379/0",
        "jwt_private_key_pem": "PRIVATE",
        "jwt_public_key_pem": "PUBLIC",
        "broker_credential_kek_b64": "S0VL",
        "razorpay_key_secret": "rzp-fallback",
        "stripe_secret_key": "stripe-fallback",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


class _StaticProvider:
    def __init__(self, values: dict[str, str]) -> None:
        self._values = values

    def get(self, name: str) -> str | None:
        return self._values.get(name)


class _BrokenProvider:
    def get(self, name: str) -> str | None:
        raise RuntimeError("backend down")


# -- EnvSecretsProvider ----------------------------------------------------


def test_env_provider_returns_override_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALGO_SECRET_JWT_PRIVATE_KEY", "from-env")
    provider = EnvSecretsProvider()
    assert provider.get("jwt_private_key") == "from-env"


def test_env_provider_blank_is_treated_as_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALGO_SECRET_JWT_PRIVATE_KEY", "   ")
    assert EnvSecretsProvider().get("jwt_private_key") is None


def test_env_provider_missing_returns_none() -> None:
    assert EnvSecretsProvider().get("nope_not_set") is None


# -- SecretsResolver fallback semantics ------------------------------------


def test_resolver_falls_back_to_settings_when_unmanaged() -> None:
    resolver = SecretsResolver(_StaticProvider({}), _settings())
    assert resolver.jwt_private_key() == "PRIVATE"
    assert resolver.jwt_public_key() == "PUBLIC"
    assert resolver.broker_credential_kek_b64() == "S0VL"
    assert resolver.razorpay_key_secret() == "rzp-fallback"
    assert resolver.stripe_secret_key() == "stripe-fallback"


def test_resolver_prefers_managed_value() -> None:
    resolver = SecretsResolver(
        _StaticProvider({"jwt_private_key": "managed", "stripe_secret_key": "managed-stripe"}),
        _settings(),
    )
    assert resolver.jwt_private_key() == "managed"
    assert resolver.stripe_secret_key() == "managed-stripe"
    # Unmanaged names still fall back.
    assert resolver.jwt_public_key() == "PUBLIC"


def test_resolver_survives_provider_failure_with_fallback() -> None:
    resolver = SecretsResolver(_BrokenProvider(), _settings())
    assert resolver.jwt_private_key() == "PRIVATE"


def test_default_backend_is_env() -> None:
    provider = build_secrets_provider(_settings())
    assert isinstance(provider, EnvSecretsProvider)


def test_aws_backend_requires_secret_id() -> None:
    with pytest.raises(ValueError, match="AWS_SECRETS_ID"):
        build_secrets_provider(_settings(secrets_backend="aws"))


def test_encrypted_backend_requires_key() -> None:
    # With no encryption key configured, construction fails closed rather than
    # silently falling back.
    with pytest.raises(RuntimeError, match="secrets encryption key"):
        build_secrets_provider(_settings(secrets_backend="encrypted"))


# -- Log redaction ---------------------------------------------------------


def test_redaction_masks_secret_keys() -> None:
    event = {
        "event": "login",
        "password": "hunter2",
        "api_key": "sk-123",
        "jwt_private_key": "PRIVATE",
        "authorization": "Bearer x",
        "user_id": "u1",
    }
    out = _redact_secrets(None, "info", dict(event))
    assert out["password"] == "***redacted***"
    assert out["api_key"] == "***redacted***"
    assert out["jwt_private_key"] == "***redacted***"
    assert out["authorization"] == "***redacted***"
    # Non-secret fields are untouched.
    assert out["event"] == "login"
    assert out["user_id"] == "u1"


def test_redaction_masks_nested_secrets() -> None:
    event = {"context": {"credential": "abc", "safe": "ok", "nested": {"token": "t"}}}
    out = _redact_secrets(None, "info", dict(event))
    assert out["context"]["credential"] == "***redacted***"
    assert out["context"]["safe"] == "ok"
    assert out["context"]["nested"]["token"] == "***redacted***"
