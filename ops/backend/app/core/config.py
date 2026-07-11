"""Application configuration.

Settings are loaded from environment variables (and an optional ``.env`` file)
via pydantic-settings. The database / Supabase fields are declared now so the
wiring is ready, but they are intentionally left unused in this milestone.
"""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    supabase_url: str | None = None
    supabase_anon_key: str | None = None

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

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_postgres_driver(cls, value: str | None) -> str | None:
        return normalize_database_url(value)

    @property
    def cors_origin_list(self) -> list[str]:
        """Parse the CORS origins string into a clean list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (single source of truth)."""
    return Settings()
