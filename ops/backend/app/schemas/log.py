"""Log schemas."""

from typing import Literal

from pydantic import BaseModel

LogSource = Literal["application", "strategy", "python", "broker", "database", "system"]
LogLevel = Literal["debug", "info", "warn", "error"]


class LogEntry(BaseModel):
    """A single structured log line."""

    id: str
    time: str
    source: LogSource
    level: LogLevel
    logger: str
    message: str
