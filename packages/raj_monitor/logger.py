"""Structured, rotating logging for the agent and SDK.

A single helper, :func:`get_logger`, returns a namespaced logger writing both to
stderr and to a size-rotated file. Rotation limits keep disk usage bounded on
long-running VPS hosts. Logging is best-effort: if the log directory cannot be
created we silently fall back to console-only so the agent still runs.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from . import constants

_configured: set[str] = set()


def get_logger(
    name: str = "raj_monitor",
    *,
    level: str = constants.DEFAULT_LOG_LEVEL,
    log_dir: str | None = constants.DEFAULT_LOG_DIR,
    max_bytes: int = constants.DEFAULT_LOG_MAX_BYTES,
    backup_count: int = constants.DEFAULT_LOG_BACKUP_COUNT,
) -> logging.Logger:
    """Return a configured logger; idempotent per ``name``."""
    logger = logging.getLogger(name)
    if name in _configured:
        return logger

    logger.setLevel(_coerce_level(level))
    logger.propagate = False

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    console = logging.StreamHandler(stream=sys.stderr)
    console.setFormatter(fmt)
    logger.addHandler(console)

    if log_dir:
        try:
            os.makedirs(log_dir, exist_ok=True)
            file_handler = RotatingFileHandler(
                os.path.join(log_dir, f"{name}.log"),
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            file_handler.setFormatter(fmt)
            logger.addHandler(file_handler)
        except OSError:
            # Disk/permission issues must not stop the agent — console only.
            logger.warning("Could not open log file in %s; logging to console only", log_dir)

    _configured.add(name)
    return logger


def _coerce_level(level: str | int) -> int:
    if isinstance(level, int):
        return level
    return getattr(logging, str(level).upper(), logging.INFO)
