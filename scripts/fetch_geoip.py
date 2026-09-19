"""Download the free DB-IP "IP to City Lite" database used for audit locations.

The database is published monthly under CC BY 4.0 (attribution: "IP geolocation
by DB-IP", https://db-ip.com). Lookups against it happen entirely on this
server; no visitor address is ever sent anywhere.

Usage:
    python scripts/fetch_geoip.py [target-path] [--max-age-days 35]

Skips the download when the existing file is newer than --max-age-days, so it is
safe to run on every deploy. Exits 0 on success or skip, 1 on failure (the API
keeps working without it; locations are just not recorded).
"""

from __future__ import annotations

import argparse
import gzip
import os
import shutil
import sys
import tempfile
import time
from datetime import UTC, date, datetime
from pathlib import Path

import httpx

DEFAULT_TARGET = Path("var/geoip/dbip-city-lite.mmdb")
URL = "https://download.db-ip.com/free/dbip-city-lite-{month}.mmdb.gz"


def _months_to_try(today: date) -> list[str]:
    # The current month's file appears a day or two into the month.
    if today.month == 1:
        previous = date(today.year - 1, 12, 1)
    else:
        previous = date(today.year, today.month - 1, 1)
    return [today.strftime("%Y-%m"), previous.strftime("%Y-%m")]


def _download(url: str, destination: Path) -> bool:
    with httpx.stream("GET", url, timeout=120.0, follow_redirects=True) as response:
        if response.status_code == 404:
            return False
        response.raise_for_status()
        with tempfile.NamedTemporaryFile(delete=False, dir=destination.parent) as gz:
            for chunk in response.iter_bytes(1 << 20):
                gz.write(chunk)
            gz_path = Path(gz.name)
    try:
        with (
            gzip.open(gz_path, "rb") as source,
            tempfile.NamedTemporaryFile(delete=False, dir=destination.parent) as out,
        ):
            shutil.copyfileobj(source, out)
            staged = Path(out.name)
        os.replace(staged, destination)  # atomic: readers never see a partial file
    finally:
        gz_path.unlink(missing_ok=True)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", nargs="?", default=str(DEFAULT_TARGET))
    parser.add_argument("--max-age-days", type=float, default=35.0)
    args = parser.parse_args()

    target = Path(args.target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        age_days = (time.time() - target.stat().st_mtime) / 86_400
        if age_days < args.max_age_days:
            print(f"[geoip] {target} is {age_days:.0f} days old; keeping it")
            return 0

    for month in _months_to_try(datetime.now(UTC).date()):
        url = URL.format(month=month)
        try:
            if _download(url, target):
                size_mb = target.stat().st_size / 1_048_576
                print(f"[geoip] installed {url} -> {target} ({size_mb:.0f} MB)")
                return 0
            print(f"[geoip] not published yet: {url}")
        except Exception as error:
            print(f"[geoip] download failed from {url}: {error}", file=sys.stderr)
    print("[geoip] no database installed; audit locations will be empty", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
