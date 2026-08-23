"""Application configuration.

Settings are loaded from environment variables (and an optional ``.env`` file)
via pydantic-settings.

Two production safety rules are enforced from here (see ``main.py``, which calls
``Settings.assert_production_ready()`` at startup):

* **No silent mock mode.** ``ENVIRONMENT=production`` without ``DATABASE_URL``
  is a fatal misconfiguration, not a quiet fallback to in-memory repositories.
* **No open ingestion.** ``ENVIRONMENT=production`` without at least one agent
  token is fatal, so the telemetry write path can never be published unauthed.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.security import hash_token


def normalize_database_url(url: str | None) -> str | None:
    """Use the installed psycopg v3 driver for standard PostgreSQL URLs."""
    if url is None:
        return None
    if url.startswith("postgres://"):
        return f"postgresql+psycopg://{url.removeprefix('postgres://')}"
    if url.startswith("postgresql://"):
        return f"postgresql+psycopg://{url.removeprefix('postgresql://')}"
    return url


class Settings(BaseSettings):
    """Strongly-typed application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application -------------------------------------------------------
    app_name: str = "Raj Quant OS API"
    version: str = "1.0.0"
    environment: str = "development"
    debug: bool = True

    # --- HTTP / CORS ------------------------------------------------------
    api_prefix: str = "/api"
    # Comma-separated list of allowed origins for the frontend(s).
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Database (declared, not yet connected) ---------------------------
    # Populate later with the Supabase Postgres connection string.
    database_url: str | None = None
    ops_database_url: str | None = None
    supabase_url: str | None = None
    supabase_anon_key: str | None = None

    @model_validator(mode="after")
    def resolve_ops_database_url(self) -> Settings:
        if not self.database_url and self.ops_database_url:
            self.database_url = normalize_database_url(self.ops_database_url)
        return self

    # --- AlgoMatrics control plane (live platform data) --------------------
    # When all three are set, the trading-domain endpoints (dashboard,
    # strategies, trades, risk, analytics, brokers, accounts) serve live data
    # from the AlgoMatrics /api/v1 API instead of the mock fixtures. Create a
    # read-scope key via POST /api/v1/api-keys.
    algomatrics_api_url: str | None = None  # e.g. http://api:8000/api/v1
    algomatrics_api_key: str | None = None
    algomatrics_org_id: str | None = None
    algomatrics_timeout_seconds: float = 5.0
    algomatrics_cache_ttl_seconds: float = 5.0

    # --- Agent ingestion credentials --------------------------------------
    # The Raj Local Agent authenticates with `X-Raj-Agent-Token`. Two forms are
    # supported and may be combined:
    #
    #   RAJ_AGENT_TOKEN   a single fleet-wide token (any machine may use it)
    #   RAJ_AGENT_TOKENS  machine-scoped credentials, comma-separated:
    #                     "gcp-trading-01:<tok>,london-vps:<tok>"
    #
    # Machine-scoped tokens are strongly preferred: a leaked token is then
    # confined to one machine's telemetry. Both are read from the environment
    # and never written back out — see `agent_token_index`.
    raj_agent_token: str | None = None
    raj_agent_tokens: str | None = None

    # --- Dashboard (websocket) credential ---------------------------------
    # Viewer credential for `/api/ws`. See app/api/dependencies/dashboard_auth.py
    # for the accepted forms and the documented limitation of a shared token.
    raj_dashboard_token: str | None = None
    # Optional: PEM public key of the platform's RS256 access tokens. When set
    # (and PyJWT is installed) platform JWTs are accepted on the websocket.
    ops_jwt_public_key: str | None = None
    ops_jwt_issuer: str | None = None
    ops_jwt_audience: str | None = None
    # Production REST dashboard APIs always require a viewer credential. This
    # flag lets staging/dev exercise the same fail-closed path without setting
    # ENVIRONMENT=production.
    ops_rest_auth_required: bool = False

    # --- Ingestion limits --------------------------------------------------
    # Envelopes accepted in one `/api/agent/batch` call. The agent's own default
    # is 200 (raj_monitor/constants.py DEFAULT_BATCH_SIZE); this ceiling gives
    # replay/queue-drain headroom while bounding a single request's work.
    ingest_max_batch_items: int = 1000
    # Retention for the idempotency table, pruned on a rolling basis. Must
    # comfortably exceed the agent's longest realistic offline window.
    ingest_dedup_retention_days: int = 7
    # Destructive retention policies. 0 = disabled. Keep policies separate so
    # operators can choose different lifetimes for high-volume telemetry,
    # operational timelines, dead letters, sessions, raw EOD bytes and derived
    # analytics. The request path never prunes these tables.
    telemetry_retention_days: int = 0
    operational_event_retention_days: int = 0
    dead_letter_retention_days: int = 0
    session_retention_days: int = 0
    # Heartbeat cadence/state thresholds. AWS does not poll Google; machine
    # health is derived from the age of the latest reported heartbeat. Keep
    # these configurable because VPS/network cadence differs by deployment.
    heartbeat_interval_seconds: float = 10.0
    heartbeat_degraded_after_seconds: float = 30.0
    heartbeat_offline_after_seconds: float = 120.0

    # --- EOD dataset landing ----------------------------------------------
    # Raw EOD market/trading datasets are stored outside telemetry tables. The
    # production backend can be swapped later behind the DatasetStorage port;
    # local filesystem storage is deterministic for development/tests.
    eod_storage_backend: str = "local"
    eod_storage_root: str = "var/eod-datasets"
    eod_max_chunk_bytes: int = 25 * 1024 * 1024
    # S3-compatible object storage. Credentials are intentionally not modeled
    # here: use the standard AWS provider chain, IRSA/workload identity, or
    # deployment-managed AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY environment
    # variables. Buckets/prefixes are identifiers, not secrets.
    eod_s3_bucket: str | None = None
    eod_s3_prefix: str = "algomatrics/eod"
    eod_s3_region: str | None = None
    eod_s3_endpoint_url: str | None = None
    eod_s3_force_path_style: bool = False
    eod_s3_server_side_encryption: str | None = None
    # 0 = disabled. Destructive retention jobs must be explicitly configured.
    eod_metadata_retention_days: int = 0
    eod_raw_retention_days: int = 0

    # --- Quant analytics / replay -----------------------------------------
    # Bounded readers keep dashboard analytics from accidentally loading a
    # multi-GB EOD object into API memory. Larger production workloads should
    # move this service behind DuckDB/object-storage scans.
    quant_max_file_bytes: int = 50 * 1024 * 1024
    quant_max_rows: int = 500_000
    quant_replay_max_points: int = 2_000
    quant_synthetic_max_steps: int = 10_000
    quant_report_retention_days: int = 0

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_postgres_driver(cls, value: str | None) -> str | None:
        return normalize_database_url(value)

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse the CORS origins string into a clean list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() in {"production", "prod"}

    @property
    def agent_token_index(self) -> dict[str, str | None]:
        """Map ``sha256(token) -> machine scope`` (``None`` means any machine).

        Only digests are kept, so a memory dump or an accidental ``repr`` of the
        index cannot yield a usable credential. Built fresh from the environment
        on each access of the cached ``Settings`` instance.
        """
        index: dict[str, str | None] = {}
        for entry in (self.raj_agent_tokens or "").split(","):
            entry = entry.strip()
            if not entry or ":" not in entry:
                continue
            machine, _, token = entry.partition(":")
            machine, token = machine.strip(), token.strip()
            if machine and token:
                index[hash_token(token)] = machine
        fleet = (self.raj_agent_token or "").strip()
        if fleet:
            index[hash_token(fleet)] = None
        return index

    @property
    def agent_auth_configured(self) -> bool:
        return bool(self.agent_token_index)

    @property
    def dashboard_auth_configured(self) -> bool:
        return bool(
            (self.raj_dashboard_token or "").strip()
            or (self.ops_jwt_public_key or "").strip()
        )

    def assert_production_ready(self) -> None:
        """Fail fast on a production configuration that would be unsafe.

        Called once at application startup. Raising here stops the container
        before it can serve a single request, which is the whole point: a silent
        in-memory or unauthenticated production start is exactly the failure
        mode this phase exists to remove.
        """
        if not self.is_production:
            return
        problems: list[str] = []
        if not self.database_url:
            problems.append(
                "DATABASE_URL is empty — refusing to start in in-memory mock mode. "
                "Telemetry would not survive a restart and deduplication would be disabled."
            )
        if not self.agent_auth_configured:
            problems.append(
                "No agent credential configured — set RAJ_AGENT_TOKENS (preferred, "
                "machine-scoped) or RAJ_AGENT_TOKEN. Refusing to expose an "
                "unauthenticated telemetry write path."
            )
        if not self.dashboard_auth_configured:
            problems.append(
                "No dashboard credential configured — set RAJ_DASHBOARD_TOKEN or "
                "OPS_JWT_PUBLIC_KEY. Refusing to serve live telemetry over an "
                "unauthenticated websocket."
            )
        storage_backend = self.eod_storage_backend.strip().lower()
        if (
            storage_backend in {"s3", "object", "object-storage", "s3-compatible"}
            and not (self.eod_s3_bucket or "").strip()
        ):
            problems.append(
                "EOD_STORAGE_BACKEND is set to object storage but EOD_S3_BUCKET "
                "is empty. Refusing to start with an unusable EOD landing store."
            )
        if problems:
            raise RuntimeError(
                "ops-api refused to start in production:\n  - " + "\n  - ".join(problems)
            )


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (single source of truth)."""
    return Settings()
