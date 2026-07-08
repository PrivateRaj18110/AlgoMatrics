"""Structured logging configuration shared by every process."""

from __future__ import annotations

import logging
import sys
from collections.abc import Mapping, Sequence
from typing import Any

import structlog

# Log event-dict keys whose values are always masked. Matched case-insensitively
# as substrings so e.g. "jwt_private_key", "authorization", "api_key" all hit.
_SECRET_KEY_MARKERS = (
    "password",
    "secret",
    "token",
    "authorization",
    "api_key",
    "apikey",
    "private_key",
    "kek",
    "credential",
    "passphrase",
)
_MASK = "***redacted***"


def configure_logging(*, level: str, env: str, service: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(message)s",
        stream=sys.stdout,
    )
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        _add_service(service, env),
        _redact_secrets,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer: structlog.types.Processor
    if env in {"local", "test"}:
        renderer = structlog.dev.ConsoleRenderer(colors=False)
    else:
        renderer = structlog.processors.JSONRenderer()
    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


def _is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in _SECRET_KEY_MARKERS)


def _redact_value(value: Any) -> Any:
    # Recurse into nested structures so a secret nested in a dict/list is masked
    # too. Keys inside nested mappings are checked the same way.
    if isinstance(value, Mapping):
        return {
            k: (_MASK if _is_secret_key(str(k)) else _redact_value(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)) and not isinstance(value, str):
        return [_redact_value(item) for item in value]
    return value


def _redact_secrets(
    _logger: structlog.types.WrappedLogger,
    _name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Mask any event-dict field whose key looks like a secret."""
    for key in list(event_dict.keys()):
        if _is_secret_key(str(key)):
            event_dict[key] = _MASK
        else:
            value = event_dict[key]
            if isinstance(value, (Mapping, Sequence)) and not isinstance(value, (str, bytes)):
                event_dict[key] = _redact_value(value)
    return event_dict


def _add_service(service: str, env: str) -> structlog.types.Processor:
    def processor(
        _logger: structlog.types.WrappedLogger,
        _name: str,
        event_dict: structlog.types.EventDict,
    ) -> structlog.types.EventDict:
        event_dict.setdefault("service", service)
        event_dict.setdefault("env", env)
        return event_dict

    return processor
