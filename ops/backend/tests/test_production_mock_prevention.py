"""Production must not serve mock fixtures or seed demo hosts."""

from __future__ import annotations

from app.core.config import get_settings
from app.core.mock_policy import allow_mock_fixtures
from app.database.seed import seed_if_empty
from app.services.telemetry_read_models import telemetry_strategies


def test_production_disables_mock_fixtures(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///ops.db")
    monkeypatch.setenv("RAJ_AGENT_TOKEN", "agent-token")
    monkeypatch.setenv("RAJ_DASHBOARD_TOKEN", "dashboard-token")
    get_settings.cache_clear()
    try:
        assert allow_mock_fixtures() is False
    finally:
        get_settings.cache_clear()


def test_production_seed_is_a_noop(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()
    try:
        assert seed_if_empty() == {"machines": 0, "trades": 0}
    finally:
        get_settings.cache_clear()


def test_telemetry_strategies_do_not_include_fixture_catalog(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()
    try:
        names = {row["name"] for row in telemetry_strategies()}
        assert "Mean Reversion FX" not in names
        assert "Gold Scalper" not in names
        assert "Momentum Breakout" not in names
    finally:
        get_settings.cache_clear()
