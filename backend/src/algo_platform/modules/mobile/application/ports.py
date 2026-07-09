"""Ports for mobile push delivery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from algo_platform.modules.mobile.domain.devices import DevicePlatform, PushMessage


@dataclass(frozen=True, slots=True)
class PushTarget:
    """A single addressable device."""

    token: str
    platform: DevicePlatform


@dataclass(frozen=True, slots=True)
class PushResult:
    """Outcome of a fan-out; ``invalid_tokens`` should be pruned by the caller."""

    delivered: int
    invalid_tokens: tuple[str, ...] = ()


class PushProvider(Protocol):
    """Sends a push message to a set of device targets."""

    async def send(self, message: PushMessage, targets: list[PushTarget]) -> PushResult: ...
