"""Unit tests for the pure backlog-driven scaling policy (Phase 19)."""

from __future__ import annotations

import pytest

from algo_platform.shared.application.scaling import (
    ScalingAction,
    ScalingConfig,
    desired_replicas,
    recommend,
)
from algo_platform.shared.infrastructure.scaling_reporter import ScalingReporter


def _config(**kw: int) -> ScalingConfig:
    params: dict[str, int] = {
        "target_backlog_per_replica": 100,
        "min_replicas": 1,
        "max_replicas": 10,
    }
    params.update(kw)
    return ScalingConfig(**params)


def test_empty_backlog_scales_to_min() -> None:
    assert desired_replicas(0, _config(min_replicas=2)) == 2
    assert desired_replicas(-5, _config(min_replicas=1)) == 1


def test_backlog_rounds_up_per_replica() -> None:
    cfg = _config(target_backlog_per_replica=100)
    assert desired_replicas(100, cfg) == 1
    assert desired_replicas(101, cfg) == 2
    assert desired_replicas(250, cfg) == 3


def test_clamps_to_max() -> None:
    assert desired_replicas(10_000, _config(max_replicas=5)) == 5


def test_respects_min_even_with_small_backlog() -> None:
    assert desired_replicas(1, _config(min_replicas=3)) == 3


def test_recommend_scale_up() -> None:
    rec = recommend(500, current_replicas=2, config=_config())
    assert rec.desired_replicas == 5
    assert rec.action is ScalingAction.UP


def test_recommend_scale_down() -> None:
    rec = recommend(50, current_replicas=4, config=_config())
    assert rec.desired_replicas == 1
    assert rec.action is ScalingAction.DOWN


def test_recommend_hold() -> None:
    rec = recommend(150, current_replicas=2, config=_config())
    assert rec.desired_replicas == 2
    assert rec.action is ScalingAction.HOLD
    assert rec.backlog == 150


@pytest.mark.parametrize(
    "kw",
    [
        {"target_backlog_per_replica": 0},
        {"min_replicas": -1},
        {"max_replicas": 0, "min_replicas": 1},
    ],
)
def test_invalid_config_rejected(kw: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        _config(**kw)


# -- reporter over a fake Redis ---------------------------------------------


class FakeRedis:
    def __init__(self, *, length: int, lags: dict[str, int]) -> None:
        self._length = length
        self._lags = lags

    async def xlen(self, stream: str) -> int:
        return self._length

    async def consumer_group_lag(self, stream: str, group: str) -> int:
        return self._lags.get(group, 0)


async def test_reporter_computes_backlog_and_desired() -> None:
    redis = FakeRedis(length=450, lags={"notification": 250, "analytics": 0})
    reporter = ScalingReporter(
        redis,  # type: ignore[arg-type]
        stream="events",
        groups=["notification", "analytics"],
        config=_config(target_backlog_per_replica=100, min_replicas=1, max_replicas=10),
    )
    assert await reporter.stream_depth() == 450
    report = await reporter.report()
    by_group = {g.group: g for g in report}
    assert by_group["notification"].backlog == 250
    assert by_group["notification"].desired_replicas == 3
    assert by_group["analytics"].desired_replicas == 1  # empty backlog -> min
