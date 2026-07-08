from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["local", "test", "staging", "production"] = "local"
    log_level: str = "INFO"
    service_name: str = "algo-api"

    # Observability. The Prometheus scrape endpoint is exposed at /metrics and is
    # expected to be reachable only from the metrics network / scraper, never the
    # public internet (enforced at the ingress/compose layer).
    metrics_enabled: bool = True
    metrics_namespace: str = "algo"
    # HTTP port on which background processes expose their Prometheus registry.
    metrics_port: int = Field(default=9100, ge=1, le=65535)

    database_url: str
    database_pool_size: int = Field(default=10, ge=1, le=100)
    redis_url: str

    jwt_issuer: str = "algo-matrics"
    jwt_audience: str = "algo-matrics-api"
    jwt_private_key_file: Path | None = None
    jwt_public_key_file: Path | None = None
    jwt_private_key_pem: str | None = None
    jwt_public_key_pem: str | None = None
    access_token_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    refresh_token_ttl_seconds: int = Field(default=2_592_000, ge=3600)
    ws_ticket_ttl_seconds: int = Field(default=60, ge=10, le=600)

    broker_credential_kek_file: Path | None = None
    broker_credential_kek_b64: str | None = None
    credential_key_version: int = 1

    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8080"]
    cookie_secure: bool = False
    cookie_domain: str | None = None

    # Public frontend origin used to build e-mail verification / password reset links.
    app_base_url: str = "http://localhost:5173"

    email_backend: Literal["console", "smtp"] = "console"
    email_from: str = "Algo Matrics <no-reply@algomatrics.local>"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = True

    razorpay_key_id: str | None = None
    razorpay_key_secret: str | None = None
    razorpay_webhook_secret: str | None = None
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    billing_currency: str = "INR"

    market_data_source: Literal["simulated"] = "simulated"
    market_tick_interval_ms: int = Field(default=1000, ge=100, le=60_000)
    market_data_seed: int = 20_260_101

    engine_poll_seconds: float = Field(default=2.0, ge=0.2, le=60.0)
    outbox_poll_seconds: float = Field(default=1.0, ge=0.1, le=60.0)
    scheduler_interval_seconds: float = Field(default=60.0, ge=5.0, le=3600.0)

    strategy_artifact_dir: Path = Path("var/artifacts")
    upload_dir: Path = Path("var/uploads")
    # Python source cannot be safely sandboxed in-process. Keep this disabled
    # outside explicitly controlled local development until an isolated runner
    # is deployed.
    allow_in_process_strategy_uploads: bool = False
    # Exact DNS names/IP literals allowed for user-configured MT5 agents.
    # Production should keep this explicit to prevent server-side request forgery.
    mt5_agent_allowed_hosts: list[str] = []

    login_rate_limit_per_minute: int = Field(default=10, ge=1)
    api_rate_limit_per_minute: int = Field(default=600, ge=10)

    def load_jwt_private_key(self) -> str:
        return self._load_key(self.jwt_private_key_pem, self.jwt_private_key_file, "JWT private")

    def load_jwt_public_key(self) -> str:
        return self._load_key(self.jwt_public_key_pem, self.jwt_public_key_file, "JWT public")

    def load_broker_kek_b64(self) -> str:
        if self.broker_credential_kek_b64:
            return self.broker_credential_kek_b64.strip()
        if self.broker_credential_kek_file and self.broker_credential_kek_file.exists():
            return self.broker_credential_kek_file.read_text(encoding="utf-8").strip()
        raise RuntimeError(
            "broker credential KEK is not configured; set BROKER_CREDENTIAL_KEK_B64 "
            "or BROKER_CREDENTIAL_KEK_FILE"
        )

    @staticmethod
    def _load_key(inline: str | None, file: Path | None, label: str) -> str:
        if inline:
            return inline.replace("\\n", "\n")
        if file and file.exists():
            return file.read_text(encoding="utf-8")
        raise RuntimeError(f"{label} key is not configured (inline PEM or key file required)")


@lru_cache
def get_settings() -> Settings:
    return Settings()
