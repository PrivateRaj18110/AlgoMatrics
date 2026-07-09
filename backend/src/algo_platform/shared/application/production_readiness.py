"""Fail-fast production configuration checks (12-Factor / OWASP hardening).

Pure so the rules are unit testable and free of the Settings object: the caller
passes the handful of flags that matter. In ``production`` a *blocking* issue
should stop the process from booting with an unsafe configuration; ``warning``
issues are logged but non-fatal. Non-production environments only ever warn.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    BLOCKING = "blocking"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class ReadinessIssue:
    code: str
    severity: Severity
    message: str


@dataclass(frozen=True, slots=True)
class ProductionConfig:
    app_env: str
    cookie_secure: bool
    cors_origins: list[str]
    security_headers_enabled: bool
    rate_limit_enabled: bool
    metrics_enabled: bool
    secrets_backend: str
    app_base_url: str


def check_readiness(config: ProductionConfig) -> list[ReadinessIssue]:
    """Return configuration issues; empty means production-safe.

    Outside ``production`` every issue is downgraded to a warning so local/test
    runs are never blocked by relaxed development defaults.
    """

    issues: list[ReadinessIssue] = []
    is_prod = config.app_env == "production"

    def add(code: str, blocking: bool, message: str) -> None:
        severity = Severity.BLOCKING if (blocking and is_prod) else Severity.WARNING
        issues.append(ReadinessIssue(code=code, severity=severity, message=message))

    if not config.cookie_secure:
        add("cookie_insecure", True, "COOKIE_SECURE must be true in production (HTTPS).")
    if "*" in config.cors_origins:
        add("cors_wildcard", True, "CORS_ORIGINS must not contain '*' in production.")
    if any(o.startswith("http://") for o in config.cors_origins):
        add("cors_plain_http", True, "CORS_ORIGINS should be https:// origins in production.")
    if not config.security_headers_enabled:
        add("security_headers_off", True, "SECURITY_HEADERS_ENABLED should be true in production.")
    if not config.rate_limit_enabled:
        add("rate_limit_off", True, "RATE_LIMIT_ENABLED should be true in production.")
    if config.secrets_backend == "env":
        add(
            "secrets_env_backend",
            True,
            "SECRETS_BACKEND should be 'aws' or 'encrypted' in production, not 'env'.",
        )
    if config.app_base_url.startswith("http://"):
        add("app_base_url_http", True, "APP_BASE_URL should be https:// in production.")
    if not config.metrics_enabled:
        add("metrics_off", False, "METRICS_ENABLED is off; observability will be limited.")
    return issues


def blocking_issues(issues: list[ReadinessIssue]) -> list[ReadinessIssue]:
    return [i for i in issues if i.severity is Severity.BLOCKING]
