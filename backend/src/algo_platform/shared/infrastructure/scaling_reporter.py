"""Report queue backlog + a scaling recommendation for worker consumer groups.

Reads consumer-group lag from Redis and applies the pure scaling policy. Used by
the admin scaling endpoint and to populate the ``stream_depth`` Prometheus gauge
that an autoscaler can also scrape.
"""

from __future__ import annotations

from dataclasses import dataclass

from algo_platform.shared.application.scaling import (
    ScalingConfig,
    desired_replicas,
)
from algo_platform.shared.infrastructure.redis_gateway import RedisGateway


@dataclass(frozen=True, slots=True)
class GroupBacklog:
    stream: str
    group: str
    backlog: int
    desired_replicas: int


class ScalingReporter:
    def __init__(
        self, redis: RedisGateway, *, stream: str, groups: list[str], config: ScalingConfig
    ) -> None:
        self._redis = redis
        self._stream = stream
        self._groups = groups
        self._config = config

    async def stream_depth(self) -> int:
        return await self._redis.xlen(self._stream)

    async def report(self) -> list[GroupBacklog]:
        out: list[GroupBacklog] = []
        for group in self._groups:
            backlog = await self._redis.consumer_group_lag(self._stream, group)
            out.append(
                GroupBacklog(
                    stream=self._stream,
                    group=group,
                    backlog=backlog,
                    desired_replicas=desired_replicas(backlog, self._config),
                )
            )
        return out
