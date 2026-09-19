"""Offline IP geolocation (city / region / country).

Reads a local MaxMind-format database (DB-IP "IP to City Lite", CC BY 4.0,
fetched by ``scripts/fetch_geoip.py``). Lookups never leave the server: no
visitor address is sent to a third-party service. With no database configured
every lookup returns None and nothing else changes.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class GeoLocation:
    country: str | None
    country_code: str | None
    region: str | None
    city: str | None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "country": self.country,
            "country_code": self.country_code,
            "region": self.region,
            "city": self.city,
        }


_PRIVATE = GeoLocation(country="Private network", country_code=None, region=None, city=None)


def _english(names: Any) -> str | None:
    if isinstance(names, dict):
        value = names.get("en")
        return str(value) if value else None
    return None


class GeoIpResolver:
    def __init__(self, database_path: str | None) -> None:
        self._reader: Any = None
        if not database_path:
            return
        path = Path(database_path)
        if not path.is_file():
            logger.warning("geoip.database_missing", path=str(path))
            return
        try:
            import maxminddb

            self._reader = maxminddb.open_database(str(path))
            logger.info("geoip.database_loaded", path=str(path))
        except Exception:
            logger.warning("geoip.database_unreadable", path=str(path))

    @property
    def available(self) -> bool:
        return self._reader is not None

    def lookup(self, ip: str | None) -> GeoLocation | None:
        if not ip:
            return None
        try:
            address = ipaddress.ip_address(ip)
        except ValueError:
            return None
        if address.is_private or address.is_loopback or address.is_link_local:
            return _PRIVATE
        if self._reader is None:
            return None
        return self._cached_lookup(str(address))

    @lru_cache(maxsize=4096)  # noqa: B019 - resolver is a process-lifetime singleton
    def _cached_lookup(self, ip: str) -> GeoLocation | None:
        try:
            record = self._reader.get(ip)
        except Exception:
            return None
        if not isinstance(record, dict):
            return None
        subdivisions = record.get("subdivisions")
        region = (
            _english(subdivisions[0].get("names"))
            if isinstance(subdivisions, list) and subdivisions
            else None
        )
        country_raw, city_raw = record.get("country"), record.get("city")
        country: dict[str, Any] = country_raw if isinstance(country_raw, dict) else {}
        city: dict[str, Any] = city_raw if isinstance(city_raw, dict) else {}
        return GeoLocation(
            country=_english(country.get("names")),
            country_code=country.get("iso_code"),
            region=region,
            city=_english(city.get("names")),
        )


_resolver: GeoIpResolver = GeoIpResolver(None)


def configure_geoip(database_path: str | None) -> GeoIpResolver:
    """Install the process-wide resolver (called once at application start)."""
    global _resolver
    _resolver = GeoIpResolver(database_path)
    return _resolver


def geoip() -> GeoIpResolver:
    return _resolver
