"""The shared gzip request middleware must be bounded.

Staging validation measured the unbounded version: a 203,910-byte request
expanded to 209,715,246 bytes of process memory — roughly 1000:1 — took 42
seconds to refuse, and then wrote the whole 200 MB to the database as preserved
evidence of a request that had already been rejected.

The middleware is shared by every protocol behind it, so these tests cover the
ceiling itself, the behaviour that must not change for legitimate traffic, and
the failure semantics: a body over the ceiling is a *terminal* 413, not a
connection reset, because the retry contract treats a reset as retryable and a
producer would resend an impossible message forever.
"""

from __future__ import annotations

import gzip
import json

import pytest
from app.middleware.gzip_request import (
    MAX_DECOMPRESSED_BYTES,
    GzipRequestMiddleware,
)
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient


@pytest.fixture
def echo_client() -> TestClient:
    """A minimal app behind the middleware, so only the middleware is under test."""
    app = FastAPI()

    @app.post("/echo")
    async def echo(request: Request) -> dict:
        body = await request.body()
        return {"length": len(body), "head": body[:32].decode("utf-8", "replace")}

    app.add_middleware(GzipRequestMiddleware)
    return TestClient(app)


def test_a_legitimate_gzipped_body_is_decompressed(echo_client: TestClient) -> None:
    payload = json.dumps({"hello": "world", "items": list(range(100))}).encode()
    response = echo_client.post(
        "/echo",
        content=gzip.compress(payload),
        headers={"Content-Encoding": "gzip", "Content-Type": "application/json"},
    )
    assert response.status_code == 200
    assert response.json()["length"] == len(payload)


def test_an_ungzipped_body_passes_through_untouched(echo_client: TestClient) -> None:
    payload = b'{"plain":"body"}'
    response = echo_client.post("/echo", content=payload)
    assert response.status_code == 200
    assert response.json()["length"] == len(payload)


def test_a_body_labelled_gzip_that_is_not_gzip_passes_through(echo_client: TestClient) -> None:
    """Long-standing documented behaviour; the ceiling must not change it."""
    payload = b'{"not":"actually gzipped"}'
    response = echo_client.post("/echo", content=payload, headers={"Content-Encoding": "gzip"})
    assert response.status_code == 200
    assert response.json()["length"] == len(payload)


def test_a_body_just_under_the_ceiling_is_still_accepted(echo_client: TestClient) -> None:
    """The ceiling must not reject legitimate large uploads.

    The largest legitimate body behind this middleware is an EOD chunk at 25
    MiB, so the ceiling has to sit above it.
    """
    payload = b"C" * (MAX_DECOMPRESSED_BYTES - 1024)
    response = echo_client.post(
        "/echo", content=gzip.compress(payload), headers={"Content-Encoding": "gzip"}
    )
    assert response.status_code == 200
    assert response.json()["length"] == len(payload)


def test_a_decompression_bomb_is_refused_with_413(echo_client: TestClient) -> None:
    """~1000:1 amplification, refused without materialising the expansion."""
    bomb = gzip.compress(b"A" * (MAX_DECOMPRESSED_BYTES + (4 * 1024 * 1024)), 9)
    assert len(bomb) < 256 * 1024, "the test bomb should be small on the wire"

    response = echo_client.post("/echo", content=bomb, headers={"Content-Encoding": "gzip"})
    assert response.status_code == 413
    detail = response.json()["detail"]
    assert detail["reason"] == "request_too_large"
    # A terminal, readable refusal — not a dropped connection.
    assert "decompressed" in detail["detail"]


def test_an_oversized_compressed_stream_is_refused_before_decompression(
    echo_client: TestClient,
) -> None:
    """More compressed bytes than the ceiling allows is refused on its own."""
    # Incompressible, so the compressed stream itself exceeds the ceiling.
    import os

    payload = os.urandom(MAX_DECOMPRESSED_BYTES + (1024 * 1024))
    response = echo_client.post(
        "/echo", content=gzip.compress(payload, 1), headers={"Content-Encoding": "gzip"}
    )
    assert response.status_code == 413
    assert response.json()["detail"]["reason"] == "request_too_large"


def test_the_ceiling_sits_above_every_legitimate_upload() -> None:
    """A regression guard on the constant itself.

    If ``eod_max_chunk_bytes`` is ever raised above the transport ceiling,
    legitimate EOD chunk uploads would start failing with 413 — which would look
    like a storage bug rather than a limit mismatch.
    """
    from app.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    assert settings.eod_max_chunk_bytes < MAX_DECOMPRESSED_BYTES
    get_settings.cache_clear()
