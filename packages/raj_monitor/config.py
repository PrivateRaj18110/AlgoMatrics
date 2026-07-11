"""Configuration loading for the Local Agent.

The user edits **one file** — ``config.yaml`` — and nothing else. This module
reads it (PyYAML if available, otherwise a tiny built-in parser for the simple
subset we use), overlays environment variables, applies defaults, and returns a
single immutable :class:`Config` object the rest of the agent consumes.

Environment overrides (handy for containers / systemd):
    RAJ_BACKEND_URL, RAJ_BACKEND_TOKEN, RAJ_MACHINE, RAJ_LOCAL_TOKEN,
    RAJ_AGENT_HOST, RAJ_AGENT_PORT
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from . import constants
from .exceptions import ConfigError

try:  # PyYAML is preferred but optional.
    import yaml  # type: ignore
    _HAS_YAML = True
except Exception:  # pragma: no cover - environment dependent
    yaml = None  # type: ignore
    _HAS_YAML = False


@dataclass(frozen=True)
class Config:
    """Resolved agent configuration (defaults + file + env)."""

    # Backend (Agent -> FastAPI)
    backend_url: str = constants.DEFAULT_BACKEND_URL
    backend_token: str = ""
    verify_ssl: bool = True
    timeout_sec: float = constants.DEFAULT_TIMEOUT

    # Machine identity
    machine_name: str = "unknown"
    location: str = ""
    provider: str = ""

    # Local agent API (SDK -> Agent)
    agent_host: str = constants.DEFAULT_AGENT_HOST
    agent_port: int = constants.DEFAULT_AGENT_PORT
    local_token: str = ""

    # Intervals
    heartbeat_sec: float = constants.DEFAULT_HEARTBEAT_INTERVAL
    metrics_sec: float = constants.DEFAULT_METRICS_INTERVAL
    upload_sec: float = constants.DEFAULT_UPLOAD_INTERVAL

    # Queue / batching
    queue_max_size: int = constants.DEFAULT_QUEUE_MAX_SIZE
    batch_size: int = constants.DEFAULT_BATCH_SIZE
    queue_db: str = constants.DEFAULT_QUEUE_DB

    # Retry / circuit breaker
    retry_count: int = constants.DEFAULT_RETRY_COUNT
    backoff_base_sec: float = constants.DEFAULT_BACKOFF_BASE
    backoff_max_sec: float = constants.DEFAULT_BACKOFF_MAX
    breaker_threshold: int = constants.DEFAULT_BREAKER_THRESHOLD
    breaker_cooldown_sec: float = constants.DEFAULT_BREAKER_COOLDOWN

    # Logging
    log_level: str = constants.DEFAULT_LOG_LEVEL
    log_dir: str = constants.DEFAULT_LOG_DIR
    log_max_bytes: int = constants.DEFAULT_LOG_MAX_BYTES
    log_backup_count: int = constants.DEFAULT_LOG_BACKUP_COUNT

    extra: dict[str, Any] = field(default_factory=dict)


def _deep_get(d: dict, *keys: str, default: Any = None) -> Any:
    cur: Any = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def load_config(path: str | None = None) -> Config:
    """Load configuration from ``path`` (defaults to ``./config.yaml``).

    A missing file is *not* fatal — the agent runs on defaults + env vars so it
    can be started in a container with only environment configuration.
    """
    path = path or os.getenv("RAJ_CONFIG", "config.yaml")
    raw: dict[str, Any] = {}
    if path and os.path.exists(path):
        raw = _parse_file(path)

    cfg = Config(
        backend_url=_env("RAJ_BACKEND_URL", _deep_get(raw, "backend", "url", default=constants.DEFAULT_BACKEND_URL)).rstrip("/"),
        backend_token=_env("RAJ_BACKEND_TOKEN", _deep_get(raw, "backend", "token", default="")),
        verify_ssl=_as_bool(_deep_get(raw, "backend", "verify_ssl", default=True)),
        timeout_sec=_as_float(_deep_get(raw, "backend", "timeout_sec", default=constants.DEFAULT_TIMEOUT)),
        machine_name=_env("RAJ_MACHINE", _deep_get(raw, "machine", "name", default="unknown")),
        location=_deep_get(raw, "machine", "location", default=""),
        provider=_deep_get(raw, "machine", "provider", default=""),
        agent_host=_env("RAJ_AGENT_HOST", _deep_get(raw, "agent", "host", default=constants.DEFAULT_AGENT_HOST)),
        agent_port=int(_env("RAJ_AGENT_PORT", _deep_get(raw, "agent", "port", default=constants.DEFAULT_AGENT_PORT))),
        local_token=_env("RAJ_LOCAL_TOKEN", _deep_get(raw, "agent", "local_token", default="")),
        heartbeat_sec=_as_float(_deep_get(raw, "intervals", "heartbeat_sec", default=constants.DEFAULT_HEARTBEAT_INTERVAL)),
        metrics_sec=_as_float(_deep_get(raw, "intervals", "metrics_sec", default=constants.DEFAULT_METRICS_INTERVAL)),
        upload_sec=_as_float(_deep_get(raw, "intervals", "upload_sec", default=constants.DEFAULT_UPLOAD_INTERVAL)),
        queue_max_size=int(_deep_get(raw, "queue", "max_size", default=constants.DEFAULT_QUEUE_MAX_SIZE)),
        batch_size=int(_deep_get(raw, "queue", "batch_size", default=constants.DEFAULT_BATCH_SIZE)),
        queue_db=_deep_get(raw, "queue", "db_path", default=constants.DEFAULT_QUEUE_DB),
        retry_count=int(_deep_get(raw, "retry", "count", default=constants.DEFAULT_RETRY_COUNT)),
        backoff_base_sec=_as_float(_deep_get(raw, "retry", "backoff_base_sec", default=constants.DEFAULT_BACKOFF_BASE)),
        backoff_max_sec=_as_float(_deep_get(raw, "retry", "backoff_max_sec", default=constants.DEFAULT_BACKOFF_MAX)),
        breaker_threshold=int(_deep_get(raw, "retry", "breaker_threshold", default=constants.DEFAULT_BREAKER_THRESHOLD)),
        breaker_cooldown_sec=_as_float(_deep_get(raw, "retry", "breaker_cooldown_sec", default=constants.DEFAULT_BREAKER_COOLDOWN)),
        log_level=_deep_get(raw, "logging", "level", default=constants.DEFAULT_LOG_LEVEL),
        log_dir=_deep_get(raw, "logging", "dir", default=constants.DEFAULT_LOG_DIR),
        log_max_bytes=int(_deep_get(raw, "logging", "max_bytes", default=constants.DEFAULT_LOG_MAX_BYTES)),
        log_backup_count=int(_deep_get(raw, "logging", "backup_count", default=constants.DEFAULT_LOG_BACKUP_COUNT)),
    )
    return cfg


def _parse_file(path: str) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:  # pragma: no cover
        raise ConfigError(f"Cannot read config file {path}: {exc}") from exc

    if _HAS_YAML:
        data = yaml.safe_load(text) or {}
        if not isinstance(data, dict):
            raise ConfigError(f"Config file {path} must contain a mapping")
        return data
    return _mini_yaml(text)


def _mini_yaml(text: str) -> dict[str, Any]:
    """Parse the simple 2-level ``key:`` / ``  key: value`` subset we ship.

    Only used when PyYAML is not installed. Supports nested mappings via
    indentation (2 spaces) and scalar values (str/int/float/bool). Lists and
    multi-line values are not supported — install PyYAML for anything richer.
    """
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict]] = [(-1, root)]
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        key, _, value = line.strip().partition(":")
        key = key.strip()
        value = value.split("#", 1)[0].strip() if value else ""

        while stack and stack[-1][0] >= indent:
            stack.pop()
        parent = stack[-1][1]

        if value == "":
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _coerce_scalar(value)
    return root


def _coerce_scalar(value: str) -> Any:
    v = value.strip().strip('"').strip("'")
    low = v.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "none", "~", ""):
        return None
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    return v


def _env(name: str, default: Any) -> Any:
    val = os.getenv(name)
    return val if val not in (None, "") else default


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
