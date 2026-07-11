"""Declarative base + shared helpers for the ORM models.

The five live telemetry entities (machines, events, logs, trades, metrics) plus
an idempotency table are mapped here. Column types are kept portable (no
PostgreSQL-only types) so the same models run on Postgres in production and on
SQLite in unit tests; ``DateTime(timezone=True)`` carries tz-aware timestamps.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import DeclarativeBase


def utcnow() -> datetime:
    """Timezone-aware UTC now (Python-side default for inserted rows)."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Shared declarative base for every Raj Quant OS table."""
