"""Regression tests for database URL normalization and psycopg driver resolution."""

from __future__ import annotations

import pytest

from app.core.config import Settings, normalize_database_url


@pytest.mark.parametrize(
    ("input_url", "expected_url"),
    [
        (
            "postgresql+asyncpg://algo:secret@postgres:5432/ops_telemetry",
            "postgresql+psycopg://algo:secret@postgres:5432/ops_telemetry",
        ),
        (
            "postgresql+psycopg2://algo:secret@postgres:5432/ops_telemetry",
            "postgresql+psycopg://algo:secret@postgres:5432/ops_telemetry",
        ),
        (
            "postgres://algo:secret@postgres:5432/ops_telemetry",
            "postgresql+psycopg://algo:secret@postgres:5432/ops_telemetry",
        ),
        (
            "postgresql://algo:secret@postgres:5432/ops_telemetry",
            "postgresql+psycopg://algo:secret@postgres:5432/ops_telemetry",
        ),
        (
            "postgresql+psycopg://algo:secret@postgres:5432/ops_telemetry",
            "postgresql+psycopg://algo:secret@postgres:5432/ops_telemetry",
        ),
        (
            "sqlite:///:memory:",
            "sqlite:///:memory:",
        ),
        (
            "sqlite:///test.db",
            "sqlite:///test.db",
        ),
        (
            "",
            None,
        ),
        (
            "   ",
            None,
        ),
        (
            None,
            None,
        ),
    ],
)
def test_normalize_database_url(input_url: str | None, expected_url: str | None) -> None:
    assert normalize_database_url(input_url) == expected_url


def test_settings_resolves_ops_database_url_with_asyncpg_scheme() -> None:
    settings = Settings(
        environment="production",
        ops_database_url="postgresql+asyncpg://algo:secret@postgres:5432/ops_telemetry",
        database_url=None,
        raj_agent_token="test-token",
        raj_dashboard_token="test-token",
    )
    assert settings.database_url == "postgresql+psycopg://algo:secret@postgres:5432/ops_telemetry"


def test_settings_resolves_database_url_with_asyncpg_scheme() -> None:
    settings = Settings(
        environment="production",
        ops_database_url=None,
        database_url="postgresql+asyncpg://algo:secret@postgres:5432/ops_telemetry",
        raj_agent_token="test-token",
        raj_dashboard_token="test-token",
    )
    assert settings.database_url == "postgresql+psycopg://algo:secret@postgres:5432/ops_telemetry"


def test_settings_prioritizes_ops_database_url_over_control_plane_database_url() -> None:
    settings = Settings(
        environment="production",
        database_url="postgresql+asyncpg://algo:secret@postgres:5432/algo",
        ops_database_url="postgresql+asyncpg://algo:secret@postgres:5432/ops_telemetry",
        raj_agent_token="test-token",
        raj_dashboard_token="test-token",
    )
    assert settings.database_url == "postgresql+psycopg://algo:secret@postgres:5432/ops_telemetry"
