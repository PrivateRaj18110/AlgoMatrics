"""AWS Secrets Manager backend.

Stores all managed secrets as a single JSON document keyed by the canonical
logical names (``jwt_private_key``, ``broker_credential_kek``, ...). Values are
cached for ``cache_ttl_seconds``; on expiry the document is refetched, which is
how a rotated secret is picked up without a process restart. If a refetch fails
but a previously loaded value exists, the stale cache is served (and logged)
rather than failing — the resolver's .env fallback still applies when there is
no cache at all.

boto3 is an optional dependency imported lazily, so env-only deployments never
need it. A client may be injected for testing.
"""

from __future__ import annotations

import json
from time import monotonic
from typing import Any, Protocol

import structlog

logger = structlog.get_logger("secrets")


class _SecretsManagerClient(Protocol):
    def get_secret_value(self, *, SecretId: str) -> dict[str, Any]: ...


class AwsSecretsManagerProvider:
    def __init__(
        self,
        *,
        secret_id: str,
        region_name: str | None = None,
        cache_ttl_seconds: int = 300,
        client: _SecretsManagerClient | None = None,
    ) -> None:
        if not secret_id:
            raise ValueError("AWS secrets backend requires AWS_SECRETS_ID")
        self._secret_id = secret_id
        self._region = region_name
        self._ttl = cache_ttl_seconds
        self._client = client
        self._cache: dict[str, str] | None = None
        self._fetched_at = 0.0

    def _get_client(self) -> _SecretsManagerClient:
        if self._client is None:
            import boto3  # lazy: only required when this backend is selected

            self._client = boto3.client("secretsmanager", region_name=self._region)
        return self._client

    def _load(self) -> dict[str, str]:
        now = monotonic()
        if self._cache is not None and (now - self._fetched_at) < self._ttl:
            return self._cache
        try:
            response = self._get_client().get_secret_value(SecretId=self._secret_id)
            raw = response.get("SecretString")
            data = json.loads(raw) if raw else {}
            if not isinstance(data, dict):
                raise ValueError("secret document is not a JSON object")
            self._cache = {str(k): str(v) for k, v in data.items()}
            self._fetched_at = now
        except Exception:
            if self._cache is not None:
                # Serve the last good values through a transient outage.
                logger.warning("secrets.aws_refresh_failed_using_cache", secret_id=self._secret_id)
                return self._cache
            raise
        return self._cache

    def get(self, name: str) -> str | None:
        value = self._load().get(name)
        return value if value else None
