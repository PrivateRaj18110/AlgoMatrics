"""Payload compression helpers.

Batches of telemetry compress well (lots of repeated keys), so the transport
gzips anything over :data:`constants.COMPRESS_MIN_BYTES`. The backend advertises
support by honouring ``Content-Encoding: gzip``; smaller payloads skip
compression to avoid wasting CPU.
"""

from __future__ import annotations

import gzip
import json
from typing import Any


def encode_json(payload: Any, *, min_bytes: int = 512) -> tuple[bytes, bool]:
    """Serialise ``payload`` to JSON bytes, gzipping if large enough.

    Returns ``(body, gzipped)`` so the caller can set ``Content-Encoding``.
    """
    raw = json.dumps(payload, separators=(",", ":"), default=str).encode("utf-8")
    if len(raw) >= min_bytes:
        return gzip.compress(raw, compresslevel=6), True
    return raw, False


def decode_json(body: bytes, *, gzipped: bool) -> Any:
    """Inverse of :func:`encode_json` — used by the backend / tests."""
    if gzipped:
        body = gzip.decompress(body)
    return json.loads(body.decode("utf-8"))
