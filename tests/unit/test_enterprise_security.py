"""Unit tests for security headers policy + IP allowlist matching (Phase 17)."""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from algo_platform.api.middleware.security_headers import SecurityHeadersMiddleware
from algo_platform.modules.organizations.domain.ip_allowlist import (
    is_ip_allowed,
    normalize_entries,
    validate_entry,
)
from algo_platform.shared.domain.errors import ValidationFailed
from algo_platform.shared.infrastructure.security_headers import security_headers

# -- security headers -------------------------------------------------------


def test_security_headers_core_set_present() -> None:
    headers = security_headers("local")
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert "Content-Security-Policy" in headers


def test_hsts_only_in_tls_environments() -> None:
    assert "Strict-Transport-Security" not in security_headers("local")
    assert "Strict-Transport-Security" not in security_headers("test")
    assert "Strict-Transport-Security" in security_headers("staging")
    assert "Strict-Transport-Security" in security_headers("production")


def test_docs_csp_relaxed_vs_api_csp() -> None:
    api = security_headers("local")["Content-Security-Policy"]
    docs = security_headers("local", is_docs=True)["Content-Security-Policy"]
    assert "script-src 'self'" in docs
    assert api != docs
    assert "default-src 'none'" in api


def _app_with_headers(app_env: str) -> Starlette:
    async def ok(_request: object) -> PlainTextResponse:
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/ping", ok)])
    app.add_middleware(SecurityHeadersMiddleware, app_env=app_env)
    return app


def test_middleware_stamps_headers_on_response() -> None:
    client = TestClient(_app_with_headers("production"))
    response = client.get("/ping")
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "Strict-Transport-Security" in response.headers


def test_middleware_omits_hsts_in_local() -> None:
    client = TestClient(_app_with_headers("local"))
    response = client.get("/ping")
    assert "Strict-Transport-Security" not in response.headers


# -- IP allowlist -----------------------------------------------------------


def test_validate_entry_normalizes_address_and_cidr() -> None:
    assert validate_entry(" 10.0.0.1 ") == "10.0.0.1"
    assert validate_entry("10.0.0.0/24") == "10.0.0.0/24"
    # Host bits are cleared with strict=False.
    assert validate_entry("10.0.0.5/24") == "10.0.0.0/24"


@pytest.mark.parametrize("bad", ["", "not-an-ip", "10.0.0.0/33", "999.1.1.1"])
def test_validate_entry_rejects_bad(bad: str) -> None:
    with pytest.raises(ValidationFailed):
        validate_entry(bad)


def test_normalize_entries_dedupes_and_preserves_order() -> None:
    assert normalize_entries(["10.0.0.1", "10.0.0.1", "192.168.0.0/16"]) == [
        "10.0.0.1",
        "192.168.0.0/16",
    ]


def test_normalize_entries_rejects_too_many() -> None:
    with pytest.raises(ValidationFailed):
        normalize_entries([f"10.0.0.{i % 256}" for i in range(101)])


def test_empty_allowlist_allows_everything() -> None:
    assert is_ip_allowed("203.0.113.5", []) is True


def test_ip_allowed_within_cidr_and_exact() -> None:
    entries = ["10.0.0.0/24", "203.0.113.7"]
    assert is_ip_allowed("10.0.0.55", entries) is True
    assert is_ip_allowed("203.0.113.7", entries) is True
    assert is_ip_allowed("10.0.1.1", entries) is False
    assert is_ip_allowed("203.0.113.8", entries) is False


def test_unparseable_ip_denied_when_allowlist_configured() -> None:
    assert is_ip_allowed("garbage", ["10.0.0.0/24"]) is False
    assert is_ip_allowed("garbage", []) is True


def test_ipv6_cidr_matching() -> None:
    entries = ["2001:db8::/32"]
    assert is_ip_allowed("2001:db8::1", entries) is True
    assert is_ip_allowed("2001:dead::1", entries) is False
