"""Risk schemas."""

from typing import Literal

from pydantic import BaseModel

from app.schemas.common import CategoryValue


class RiskLimit(BaseModel):
    label: str
    used: float | None = None
    limit: float | None = None
    unit: Literal["currency", "percent"]


class RiskData(BaseModel):
    """Aggregated risk posture across the book."""

    dailyLoss: RiskLimit
    weeklyLoss: RiskLimit
    monthlyLoss: RiskLimit
    currentExposure: float | None = None
    maxExposure: float | None = None
    currentMargin: float | None = None
    marginLevelPct: float | None = None
    currentDrawdownPct: float | None = None
    maxDrawdownPct: float | None = None
    valueAtRisk: float | None = None
    exposureBySymbol: list[CategoryValue]
    exposureByStrategy: list[CategoryValue]
    exposureByBroker: list[CategoryValue]
