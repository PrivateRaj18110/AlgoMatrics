"""Shared schema primitives used across the domain models.

These mirror the TypeScript types in ``frontend/src/types`` so the mock
backend and the React client speak exactly the same shapes.
"""

from typing import Literal

from pydantic import BaseModel

Status = Literal["online", "degraded", "offline", "unknown"]
Trend = Literal["up", "down", "flat"]
Severity = Literal["info", "warning", "critical"]


class TimeSeriesPoint(BaseModel):
    """A single point on a time-series chart."""

    t: str
    v: float


class CategoryValue(BaseModel):
    """A labelled value pair for categorical charts."""

    label: str
    value: float
