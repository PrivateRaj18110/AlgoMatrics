"""Risk schemas."""

from typing import Literal

from pydantic import BaseModel

from app.schemas.common import CategoryValue


class RiskLimit(BaseModel):
    label: str
    used: float
    limit: float
    unit: Literal["currency", "percent"]


class RiskData(BaseModel):
    """Aggregated risk posture across the book."""

    dailyLoss: RiskLimit
    weeklyLoss: RiskLimit
    monthlyLoss: RiskLimit
    currentExposure: float
    maxExposure: float
    currentMargin: float
    marginLevelPct: float
    currentDrawdownPct: float
    maxDrawdownPct: float
    valueAtRisk: float
    exposureBySymbol: list[CategoryValue]
    exposureByStrategy: list[CategoryValue]
    exposureByBroker: list[CategoryValue]
