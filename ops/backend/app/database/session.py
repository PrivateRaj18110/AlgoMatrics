"""Database session scaffolding.

The engine / session factory are created lazily on first use so the rest of the
app can import this module without a live database. They activate only once
``DATABASE_URL`` is configured; with it unset the app runs entirely on the
in-memory mock repositories (see ``app/repositories``).
"""

from collections.abc import Iterator
from typing import Optional

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings, normalize_database_url

_engine: Optional[Engine] = None
_SessionLocal: Optional[sessionmaker[Session]] = None


def database_enabled() -> bool:
    """True when a database URL is configured (Postgres-backed mode)."""
    return bool(get_settings().database_url)


def _init() -> None:
    """Create the engine + session factory on first use."""
    global _engine, _SessionLocal
    settings = get_settings()
    if not settings.database_url:
        raise RuntimeError(
            "DATABASE_URL is not configured. The database layer is not enabled in this build."
        )
    url = normalize_database_url(settings.database_url)
    assert url is not None
    # SQLite (tests/dev) needs check_same_thread off for the threaded server;
    # Postgres gets a real connection pool sized for the API + ingest workload.
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
        _engine = create_engine(url, future=True, pool_pre_ping=True, connect_args=connect_args)
    else:
        _engine = create_engine(
            url,
            future=True,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            pool_recycle=1800,
        )
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False, future=True)


def get_engine() -> Engine:
    """Return the lazily-initialised engine."""
    if _engine is None:
        _init()
    assert _engine is not None
    return _engine


def get_sessionmaker() -> "sessionmaker[Session]":
    """Return the lazily-initialised session factory (used by the repositories)."""
    if _SessionLocal is None:
        _init()
    assert _SessionLocal is not None
    return _SessionLocal


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a database session (once DB is enabled)."""
    sm = get_sessionmaker()
    db = sm()
    try:
        yield db
    finally:
        db.close()
