"""Credential primitives for the ingestion layer.

These mirror the platform's ``algo_platform.shared.infrastructure.security``
conventions (SHA-256 digest at rest, constant-time comparison) but are
re-implemented here on purpose: ``ops-api`` is a separately built and separately
deployed container that does **not** import ``algo_platform``. Reaching across
that boundary would couple two independently released services and pull the
whole platform dependency tree into this image. The functions are three lines
each; the duplication is cheaper than the coupling.

Nothing here ever logs, formats or returns a secret value.
"""

from __future__ import annotations

import hashlib
import hmac


def hash_token(token: str) -> str:
    """SHA-256 hex digest of a token — the only form kept in memory at rest."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(left: str, right: str) -> bool:
    """Compare two strings without leaking their contents through timing."""
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def token_matches(provided: str, expected_hash: str) -> bool:
    """True when ``provided`` hashes to ``expected_hash``.

    Hashing first means the plaintext credential is compared as a fixed-width
    digest, so the comparison time never depends on how many leading characters
    of the real token an attacker guessed correctly.
    """
    return constant_time_equals(hash_token(provided), expected_hash)
