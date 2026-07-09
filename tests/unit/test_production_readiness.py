"""Unit tests for the pure production configuration checks (Phase 20)."""

from __future__ import annotations

from algo_platform.shared.application.production_readiness import (
    ProductionConfig,
    Severity,
    blocking_issues,
    check_readiness,
)


def _prod(**kw: object) -> ProductionConfig:
    params: dict[str, object] = {
        "app_env": "production",
        "cookie_secure": True,
        "cors_origins": ["https://app.example.com"],
        "security_headers_enabled": True,
        "rate_limit_enabled": True,
        "metrics_enabled": True,
        "secrets_backend": "aws",
        "app_base_url": "https://app.example.com",
    }
    params.update(kw)
    return ProductionConfig(**params)  # type: ignore[arg-type]


def test_hardened_production_config_has_no_issues() -> None:
    assert check_readiness(_prod()) == []


def test_insecure_cookie_blocks_in_production() -> None:
    issues = check_readiness(_prod(cookie_secure=False))
    codes = {i.code: i.severity for i in issues}
    assert codes["cookie_insecure"] is Severity.BLOCKING


def test_cors_wildcard_and_plain_http_block() -> None:
    issues = check_readiness(_prod(cors_origins=["*"]))
    assert any(i.code == "cors_wildcard" and i.severity is Severity.BLOCKING for i in issues)
    http = check_readiness(_prod(cors_origins=["http://app.example.com"]))
    assert any(i.code == "cors_plain_http" and i.severity is Severity.BLOCKING for i in http)


def test_env_secrets_backend_blocks_in_production() -> None:
    issues = check_readiness(_prod(secrets_backend="env"))
    assert any(i.code == "secrets_env_backend" and i.severity is Severity.BLOCKING for i in issues)


def test_metrics_off_is_only_a_warning() -> None:
    issues = check_readiness(_prod(metrics_enabled=False))
    metrics = [i for i in issues if i.code == "metrics_off"]
    assert metrics and metrics[0].severity is Severity.WARNING
    assert blocking_issues(issues) == []


def test_non_production_downgrades_everything_to_warning() -> None:
    issues = check_readiness(
        ProductionConfig(
            app_env="local",
            cookie_secure=False,
            cors_origins=["*", "http://localhost:5173"],
            security_headers_enabled=False,
            rate_limit_enabled=False,
            metrics_enabled=False,
            secrets_backend="env",
            app_base_url="http://localhost:5173",
        )
    )
    assert issues  # problems are reported
    assert blocking_issues(issues) == []  # but none block outside production


def test_staging_is_not_blocked() -> None:
    issues = check_readiness(_prod(app_env="staging", cookie_secure=False))
    assert blocking_issues(issues) == []
