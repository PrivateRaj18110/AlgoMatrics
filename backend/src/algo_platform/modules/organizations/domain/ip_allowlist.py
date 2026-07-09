"""Organization IP allowlist rules (pure).

An empty allowlist means unrestricted access (the default — no behaviour change
for existing organizations). Once entries exist, a request IP must fall inside
one of them. IPv4 and IPv6 CIDR ranges and bare addresses are supported.
"""

from __future__ import annotations

import ipaddress

from algo_platform.shared.domain.errors import ValidationFailed

_MAX_ENTRIES = 100


def validate_entry(entry: str) -> str:
    """Normalise a single allowlist entry (address or CIDR); raise if invalid."""

    text = entry.strip()
    if not text:
        raise ValidationFailed("allowlist entry must not be empty")
    try:
        if "/" in text:
            return str(ipaddress.ip_network(text, strict=False))
        return str(ipaddress.ip_address(text))
    except ValueError as exc:
        raise ValidationFailed(f"invalid IP or CIDR: {entry!r}") from exc


def normalize_entries(entries: list[str]) -> list[str]:
    """Validate and de-duplicate entries, preserving order."""

    if len(entries) > _MAX_ENTRIES:
        raise ValidationFailed(f"at most {_MAX_ENTRIES} allowlist entries are allowed")
    seen: dict[str, None] = {}
    for entry in entries:
        seen.setdefault(validate_entry(entry), None)
    return list(seen)


def is_ip_allowed(ip: str, entries: list[str]) -> bool:
    """True if ``ip`` is permitted. Empty allowlist ⇒ allowed.

    An unparseable request IP is denied when an allowlist is configured (fail
    closed) and allowed when there is no allowlist.
    """

    if not entries:
        return True
    try:
        address = ipaddress.ip_address(ip.strip())
    except ValueError:
        return False
    for entry in entries:
        try:
            if "/" in entry:
                if address in ipaddress.ip_network(entry, strict=False):
                    return True
            elif address == ipaddress.ip_address(entry):
                return True
        except ValueError:
            continue
    return False
