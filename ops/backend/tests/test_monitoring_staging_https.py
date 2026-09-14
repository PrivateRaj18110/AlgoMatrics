"""The receiver as deployed: over HTTPS, against PostgreSQL, from outside.

Everything else in the suite runs in-process. This module runs against a real
staging deployment over a real TLS connection, because several properties only
exist at that boundary: what a hostile client can actually reach, what status
an unauthenticated caller really gets, whether a credential can leak into a
response body, and whether the transport rejects oversized input before the
application sees it.

Skipped unless ``MONITORING_STAGING_ENDPOINT`` names a running staging
receiver. Requires:

    MONITORING_STAGING_ENDPOINT   https://host:port/api/monitoring/v1/messages
    MONITORING_STAGING_TOKEN      publisher token for ``lls-contract-fixture``
    MONITORING_STAGING_CA         CA file that validates the staging certificate

Optional, enabling further cases:

    MONITORING_STAGING_OTHER_TOKEN   publisher token for a different source
    MONITORING_STAGING_ADMIN_TOKEN   administrator token
    MONITORING_STAGING_AGENT_TOKEN   agent-protocol token (must not work here)

Never point this at production. It publishes messages and reads quarantine.
"""

from __future__ import annotations

import hashlib
import json
import os
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

ENDPOINT = os.environ.get("MONITORING_STAGING_ENDPOINT", "").strip()
TOKEN = os.environ.get("MONITORING_STAGING_TOKEN", "").strip()
CA_FILE = os.environ.get("MONITORING_STAGING_CA", "").strip()
OTHER_TOKEN = os.environ.get("MONITORING_STAGING_OTHER_TOKEN", "").strip()
ADMIN_TOKEN = os.environ.get("MONITORING_STAGING_ADMIN_TOKEN", "").strip()
AGENT_TOKEN = os.environ.get("MONITORING_STAGING_AGENT_TOKEN", "").strip()

pytestmark = pytest.mark.skipif(
    not (ENDPOINT and TOKEN),
    reason="MONITORING_STAGING_ENDPOINT / MONITORING_STAGING_TOKEN are not set",
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO = BACKEND_DIR.parents[1]
MESSAGES = REPO / "tests" / "fixtures" / "lls-monitoring-v1-handoff" / "fixtures" / "messages"

BASE = ENDPOINT.rsplit("/messages", 1)[0] if ENDPOINT else ""

# The whole credential set, so a response can be checked for leaking any of it.
SECRETS = [value for value in (TOKEN, OTHER_TOKEN, ADMIN_TOKEN, AGENT_TOKEN) if value]


def _context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=CA_FILE or None)


def request(
    url: str,
    *,
    method: str = "GET",
    body: bytes | None = None,
    token: str | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, bytes]:
    """One HTTPS request. Returns (status, body) for success and failure alike."""
    all_headers = dict(headers or {})
    if token is not None:
        all_headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        all_headers.setdefault("Content-Type", "application/json")
    # S310 on both lines: the URL is this test's own staging endpoint, taken
    # from an environment variable the operator set. No untrusted input reaches it.
    req = urllib.request.Request(url, data=body, method=method, headers=all_headers)  # noqa: S310
    try:
        with urllib.request.urlopen(req, context=_context(), timeout=60) as response:  # noqa: S310
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def post_message(
    raw: bytes, *, token: str | None = TOKEN, digest: str | None = None, **headers: str
) -> tuple[int, bytes]:
    sent = dict(headers)
    if digest is not None:
        sent["X-Monitoring-SHA256"] = digest
    return request(ENDPOINT, method="POST", body=raw, token=token, headers=sent)


def fixture_bytes(name: str) -> bytes:
    return (MESSAGES / name).read_bytes()


def body_text(payload: bytes) -> str:
    return payload.decode("utf-8", "replace")


def assert_no_credential_leak(payload: bytes) -> None:
    text = body_text(payload)
    for secret in SECRETS:
        assert secret not in text, "a credential appeared in a response body"


# --------------------------------------------------------------------------- #
# The deployment is what we think it is
# --------------------------------------------------------------------------- #
def test_staging_receiver_is_reachable_over_tls_and_says_it_is_staging() -> None:
    status, payload = request(f"{BASE}/health")
    assert status == 200
    health = json.loads(payload)
    assert health["receiver"] == "monitoring.v1"
    assert health["supportedSchemaVersion"] == "monitoring.v1"
    # The contract must be loadable in the deployed artefact, not just in the
    # source tree — a receiver that cannot validate must not accept anything.
    assert health["contractAvailable"] is True
    assert health["storageConfigured"] is True
    assert health["receiverDeploymentEnvironment"] == "staging"
    # The receiver never renders a verdict on LLS.
    assert health["llsHealth"] == "NOT_DETERMINED_HERE"


# --------------------------------------------------------------------------- #
# Authentication
# --------------------------------------------------------------------------- #
def test_a_valid_publisher_token_is_accepted() -> None:
    status, payload = post_message(fixture_bytes("valid_snapshot.json"))
    assert status == 200, body_text(payload)
    ack = json.loads(payload)
    assert ack["status"] in {"accepted", "duplicate"}
    assert ack["schema_version"] == "monitoring.ack.v1"


@pytest.mark.parametrize(
    ("label", "token", "headers"),
    [
        ("no credential", None, {}),
        ("empty bearer", "", {}),
        ("wrong token", "not-a-real-token", {}),
        ("token with a valid prefix", "stg", {}),
    ],
)
def test_unauthenticated_upload_is_refused(
    label: str, token: str | None, headers: dict[str, str]
) -> None:
    status, payload = post_message(fixture_bytes("valid_snapshot.json"), token=token, **headers)
    assert status == 401, f"{label}: {status}"
    assert_no_credential_leak(payload)
    # The failure must not say how far the caller got.
    assert "monitoring upload authentication required" in body_text(payload)


@pytest.mark.skipif(not AGENT_TOKEN, reason="MONITORING_STAGING_AGENT_TOKEN is not set")
def test_an_agent_protocol_token_cannot_publish_monitoring_data() -> None:
    """The two protocols' security boundaries must not merge."""
    status, payload = post_message(fixture_bytes("valid_snapshot.json"), token=AGENT_TOKEN)
    assert status == 401
    assert_no_credential_leak(payload)


@pytest.mark.skipif(not OTHER_TOKEN, reason="MONITORING_STAGING_OTHER_TOKEN is not set")
def test_a_credential_cannot_publish_another_sources_data() -> None:
    """Authenticated, but not for this ``source_id``: 403, not 401 and not 200."""
    status, payload = post_message(fixture_bytes("valid_snapshot.json"), token=OTHER_TOKEN)
    assert status == 403, body_text(payload)
    assert json.loads(payload)["detail"]["reason"] == "source_not_authorized"
    assert_no_credential_leak(payload)


def test_a_publisher_cannot_read_quarantine() -> None:
    """Upload-only means upload-only: no read access, no administrative access."""
    status, payload = request(f"{BASE}/quarantine", token=TOKEN)
    assert status == 401, body_text(payload)
    assert_no_credential_leak(payload)


@pytest.mark.skipif(not ADMIN_TOKEN, reason="MONITORING_STAGING_ADMIN_TOKEN is not set")
def test_an_administrator_can_read_quarantine() -> None:
    status, payload = request(f"{BASE}/quarantine", token=ADMIN_TOKEN)
    assert status == 200, body_text(payload)
    assert "items" in json.loads(payload)
    assert_no_credential_leak(payload)


# --------------------------------------------------------------------------- #
# Hostile input
# --------------------------------------------------------------------------- #
def _valid_document() -> dict[str, Any]:
    return json.loads(fixture_bytes("valid_snapshot.json"))


HOSTILE: list[tuple[str, bytes, set[int]]] = [
    ("not JSON at all", b"this is not json", {400}),
    ("truncated JSON", b'{"schema_version": "monitoring.v1"', {400}),
    ("a JSON array, not an object", b"[1,2,3]", {400, 422}),
    ("a bare string", b'"hello"', {400, 422}),
    ("null body", b"null", {400, 422}),
    ("empty body", b"", {400}),
    ("non-finite number", b'{"schema_version":"monitoring.v1","x":NaN}', {400}),
    ("Infinity", b'{"schema_version":"monitoring.v1","x":Infinity}', {400}),
    ("invalid UTF-8", b'{"schema_version":"\xff\xfe"}', {400}),
    (
        "SQL injection in a string field",
        json.dumps(
            {**_valid_document(), "source_instance": "x'; DROP TABLE monitoring_evidence;--"}
        ).encode(),
        {400, 403, 422},
    ),
    (
        "SQL injection in source_id",
        json.dumps(
            {**_valid_document(), "source_id": "'; DELETE FROM monitoring_evidence;--"}
        ).encode(),
        {400, 403, 422},
    ),
    (
        "unsupported schema version",
        json.dumps({**_valid_document(), "schema_version": "monitoring.v2"}).encode(),
        {400, 422},
    ),
    (
        "forged message_id",
        json.dumps({**_valid_document(), "message_id": "mon1/" + "0" * 64}).encode(),
        {400},
    ),
    (
        "deeply nested",
        json.dumps({"schema_version": "monitoring.v1", "a": None}).encode(),
        {400, 422},
    ),
]


@pytest.mark.parametrize(("label", "raw", "acceptable"), HOSTILE, ids=[row[0] for row in HOSTILE])
def test_hostile_input_is_refused_without_leaking_anything(
    label: str, raw: bytes, acceptable: set[int]
) -> None:
    status, payload = post_message(raw)
    assert status in acceptable, f"{label}: got {status} — {body_text(payload)[:200]}"
    assert status != 200, f"{label} was accepted"
    assert_no_credential_leak(payload)
    text = body_text(payload)
    # No stack traces, no server paths, no SQL.
    assert "Traceback" not in text
    assert "site-packages" not in text
    assert "psycopg" not in text.lower()


def test_a_deeply_nested_document_is_refused_not_crashed() -> None:
    """Nesting is bounded; exceeding it must be a refusal, not a recursion error."""
    document: Any = {"depth": 0}
    for _ in range(200):
        document = {"nested": document}
    raw = json.dumps({**_valid_document(), "payload": document}).encode()
    status, payload = post_message(raw)
    assert status in {400, 413, 422}, body_text(payload)[:200]
    assert "RecursionError" not in body_text(payload)


def test_an_oversized_body_is_refused() -> None:
    """Over the contract's 1 MiB request ceiling."""
    document = _valid_document()
    document["payload"] = {"filler": "A" * (2 * 1024 * 1024)}
    status, payload = post_message(json.dumps(document).encode())
    assert status == 413, f"{status}: {body_text(payload)[:200]}"


def test_a_tampered_request_digest_is_refused() -> None:
    status, payload = post_message(fixture_bytes("valid_events.json"), digest="0" * 64)
    assert status == 400
    assert json.loads(payload)["detail"]["reason"] == "request_digest_mismatch"


def test_a_correct_request_digest_is_accepted() -> None:
    raw = fixture_bytes("valid_snapshot.json")
    status, payload = post_message(raw, digest=hashlib.sha256(raw).hexdigest())
    assert status == 200, body_text(payload)


# --------------------------------------------------------------------------- #
# Nothing here can touch trading
# --------------------------------------------------------------------------- #
def test_the_monitoring_surface_exposes_no_control_verb() -> None:
    """Read the deployed OpenAPI surface, not the source tree.

    A control path that exists but is "not wired up" is still a control path.
    This asserts against what the running deployment actually publishes.
    """
    status, payload = request(f"{BASE.rsplit('/api/', 1)[0]}/openapi.json")
    if status != 200:
        pytest.skip(f"OpenAPI document is not exposed on this deployment ({status})")

    document = json.loads(payload)
    monitoring_paths = {
        path: spec for path, spec in document.get("paths", {}).items() if "/monitoring/" in path
    }
    assert monitoring_paths, "no monitoring paths found in the deployed OpenAPI document"

    forbidden = (
        "order",
        "cancel",
        "halt",
        "pause",
        "resume",
        "kill",
        "execute",
        "trade",
        "position",
        "risk",
        "broker",
        "strategy",
        "sizing",
        "liquidate",
        "flatten",
    )
    for path, spec in monitoring_paths.items():
        for verb in spec:
            if verb.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            haystack = f"{path} {spec[verb].get('operationId', '')}".lower()
            for word in forbidden:
                assert word not in haystack, f"{verb.upper()} {path} looks like a control verb"

    # The only write path is the ingress itself.
    writers = {
        (verb.upper(), path)
        for path, spec in monitoring_paths.items()
        for verb in spec
        if verb.lower() in {"post", "put", "patch", "delete"}
    }
    assert writers == {("POST", "/api/monitoring/v1/messages")}, writers
