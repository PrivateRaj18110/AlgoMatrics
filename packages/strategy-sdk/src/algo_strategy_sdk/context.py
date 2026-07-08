from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Protocol

ParamValue = str | int | float | bool


class StrategyContext(Protocol):
    """Capability-limited runtime API supplied by the platform."""

    @property
    def now(self) -> datetime: ...

    @property
    def params(self) -> Mapping[str, ParamValue]:
        """Validated runtime parameters declared in the strategy manifest."""
        ...

    async def subscribe_ticks(self, *instruments: str) -> None: ...

    async def subscribe_candles(self, instrument: str, *timeframes: str) -> None: ...

    async def emit_signal(
        self,
        *,
        name: str,
        instrument: str,
        strength: Decimal,
        attributes: dict[str, str | int | float | bool] | None = None,
    ) -> None: ...

    async def request_order(
        self,
        *,
        instrument: str,
        side: str,
        quantity: Decimal,
        order_type: str = "market",
        limit_price: Decimal | None = None,
        stop_price: Decimal | None = None,
    ) -> str: ...

    async def cancel_order(self, client_order_id: str) -> None: ...

    async def get_position(self, instrument: str) -> Decimal:
        """Signed net quantity for the given instrument (0 when flat)."""
        ...

    async def log(self, message: str, *, level: str = "info") -> None: ...

    def state_get(self, key: str, default: object = None) -> object: ...

    async def state_set(self, key: str, value: object) -> None: ...
