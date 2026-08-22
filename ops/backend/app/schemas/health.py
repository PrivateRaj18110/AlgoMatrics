"""Pydantic schemas for the health endpoint."""

from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Response model for ``GET /api/health``."""

    status: str = Field(..., examples=["ok"], description="Service health status.")
    version: str = Field(..., examples=["1.0.0"], description="API version.")
    time: datetime = Field(..., description="Current server time (UTC, ISO-8601).")
    environment: str = Field(..., examples=["development"], description="Deployment environment.")
