"""Unit tests for the AWS Secrets Manager backend (Phase 2, slice B).

boto3 is never imported: a fake client is injected, exercising caching,
rotation-on-TTL-expiry, and stale-cache-on-error behaviour.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from algo_platform.shared.infrastructure.secrets.aws import AwsSecretsManagerProvider


class _FakeClient:
    def __init__(self, document: dict[str, str]) -> None:
        self.document = document
        self.calls = 0
        self.fail = False

    def get_secret_value(self, *, SecretId: str) -> dict[str, Any]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("secretsmanager unavailable")
        return {"SecretString": json.dumps(self.document)}


def test_reads_named_secret_from_json_document() -> None:
    client = _FakeClient({"jwt_private_key": "PRIV", "broker_credential_kek": "KEK"})
    provider = AwsSecretsManagerProvider(secret_id="algo/prod", client=client)
    assert provider.get("jwt_private_key") == "PRIV"
    assert provider.get("broker_credential_kek") == "KEK"
    assert provider.get("absent") is None


def test_values_are_cached_within_ttl() -> None:
    client = _FakeClient({"a": "1"})
    provider = AwsSecretsManagerProvider(secret_id="s", client=client, cache_ttl_seconds=300)
    provider.get("a")
    provider.get("a")
    assert client.calls == 1  # second read served from cache


def test_rotation_picked_up_after_ttl_expiry() -> None:
    client = _FakeClient({"a": "1"})
    provider = AwsSecretsManagerProvider(secret_id="s", client=client, cache_ttl_seconds=0)
    assert provider.get("a") == "1"
    client.document = {"a": "2"}  # simulate rotation
    assert provider.get("a") == "2"
    assert client.calls == 2


def test_stale_cache_served_on_refresh_error() -> None:
    client = _FakeClient({"a": "1"})
    provider = AwsSecretsManagerProvider(secret_id="s", client=client, cache_ttl_seconds=0)
    assert provider.get("a") == "1"
    client.fail = True
    # TTL is 0 so this forces a refetch, which fails; stale value is served.
    assert provider.get("a") == "1"


def test_error_without_cache_propagates() -> None:
    client = _FakeClient({"a": "1"})
    client.fail = True
    provider = AwsSecretsManagerProvider(secret_id="s", client=client)
    with pytest.raises(RuntimeError):
        provider.get("a")


def test_empty_secret_id_rejected() -> None:
    with pytest.raises(ValueError, match="AWS_SECRETS_ID"):
        AwsSecretsManagerProvider(secret_id="")
