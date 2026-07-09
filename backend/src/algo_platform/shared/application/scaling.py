"""Pure horizontal-scaling math for backlog-driven workers.

Given a queue backlog (consumer-group lag) and a target amount of work per
replica, compute the desired replica count. Kept pure so the policy — and the
recommendation an autoscaler or operator acts on — is unit testable and free of
any Redis/Prometheus dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import ceil


class ScalingAction(StrEnum):
    UP = "scale_up"
    DOWN = "scale_down"
    HOLD = "hold"


@dataclass(frozen=True, slots=True)
class ScalingConfig:
    target_backlog_per_replica: int = 100
    min_replicas: int = 1
    max_replicas: int = 10

    def __post_init__(self) -> None:
        if self.target_backlog_per_replica < 1:
            raise ValueError("target_backlog_per_replica must be >= 1")
        if self.min_replicas < 0:
            raise ValueError("min_replicas must be >= 0")
        if self.max_replicas < self.min_replicas:
            raise ValueError("max_replicas must be >= min_replicas")


@dataclass(frozen=True, slots=True)
class ScalingRecommendation:
    backlog: int
    current_replicas: int
    desired_replicas: int
    action: ScalingAction


def desired_replicas(backlog: int, config: ScalingConfig) -> int:
    """Replicas needed to drain ``backlog`` at the configured target, clamped."""

    if backlog <= 0:
        return config.min_replicas
    raw = ceil(backlog / config.target_backlog_per_replica)
    return max(config.min_replicas, min(config.max_replicas, raw))


def recommend(
    backlog: int, current_replicas: int, config: ScalingConfig
) -> ScalingRecommendation:
    desired = desired_replicas(backlog, config)
    if desired > current_replicas:
        action = ScalingAction.UP
    elif desired < current_replicas:
        action = ScalingAction.DOWN
    else:
        action = ScalingAction.HOLD
    return ScalingRecommendation(
        backlog=max(0, backlog),
        current_replicas=current_replicas,
        desired_replicas=desired,
        action=action,
    )
