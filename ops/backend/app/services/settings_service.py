"""Settings service.

Holds application settings in memory for this milestone. Once Supabase is wired
up, ``get``/``save`` persist to the database instead — the router contract is
unchanged.
"""

from __future__ import annotations

from app.schemas.settings import AppSettings

_settings = AppSettings()


def get_settings_doc() -> AppSettings:
    """Return the current application settings."""
    return _settings


def save_settings_doc(settings: AppSettings) -> AppSettings:
    """Persist (in memory) and return the updated settings."""
    global _settings
    _settings = settings
    return _settings
