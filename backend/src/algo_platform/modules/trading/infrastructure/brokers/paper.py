"""Deterministic paper-execution simulator.

This is the platform's built-in simulated venue for paper trading. Fills are
reproducible: slippage, partial-fill behavior, and latency derive from a
seeded RNG keyed by the order id, so replaying the same order stream against
the same tick stream produces identical results.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from algo_platform.modules.trading.domain.orders import OrderType
from algo_platform.shared.domain.types import Side

_BPS = Decimal("0.0001")
_PRICE_QUANTUM = Decimal("0.0001")


@dataclass(frozen=True, slots=True)
class PaperFill:
    quantity: Decimal
    price: Decimal
    fee: Decimal


@dataclass(frozen=True, slots=True)
class PaperMarketState:
    bid: Decimal
    ask: Decimal

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / 2


class PaperExecutionSimulator:
    def __init__(
        self,
        *,
        fee_rate_bps: Decimal = Decimal("2.5"),
        max_slippage_bps: Decimal = Decimal("2.0"),
        partial_fill_probability: float = 0.15,
        seed: int = 0,
    ) -> None:
        self._fee_rate = fee_rate_bps * _BPS
        self._max_slippage_bps = max_slippage_bps
        self._partial_fill_probability = partial_fill_probability
        self._seed = seed

    def _rng(self, order_id: UUID, salt: int = 0) -> random.Random:
        return random.Random((order_id.int ^ self._seed) + salt)  # noqa: S311

    def fill_market_order(
        self,
        *,
        order_id: UUID,
        side: Side,
        remaining_quantity: Decimal,
        market: PaperMarketState,
        fill_round: int = 0,
    ) -> PaperFill:
        """Fill (part of) a market order at touch price plus adverse slippage."""
        rng = self._rng(order_id, salt=fill_round)
        touch = market.ask if side is Side.BUY else market.bid
        slippage_bps = Decimal(str(rng.uniform(0, float(self._max_slippage_bps))))
        adjustment = touch * slippage_bps * _BPS
        price = touch + adjustment if side is Side.BUY else touch - adjustment
        price = max(price, _PRICE_QUANTUM).quantize(_PRICE_QUANTUM, rounding=ROUND_HALF_UP)

        quantity = remaining_quantity
        if (
            fill_round == 0
            and remaining_quantity > 1
            and rng.random() < self._partial_fill_probability
        ):
            fraction = Decimal(str(rng.uniform(0.3, 0.8)))
            quantity = (remaining_quantity * fraction).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
            quantity = max(min(quantity, remaining_quantity), Decimal("0.0001"))

        fee = (quantity * price * self._fee_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return PaperFill(quantity=quantity, price=price, fee=fee)

    def try_fill_limit_order(
        self,
        *,
        order_id: UUID,
        side: Side,
        remaining_quantity: Decimal,
        limit_price: Decimal,
        market: PaperMarketState,
    ) -> PaperFill | None:
        """Limit orders fill at the limit when the opposite touch crosses it."""
        crossed = market.ask <= limit_price if side is Side.BUY else market.bid >= limit_price
        if not crossed:
            return None
        fee = (remaining_quantity * limit_price * self._fee_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return PaperFill(quantity=remaining_quantity, price=limit_price, fee=fee)

    def stop_triggered(self, *, side: Side, stop_price: Decimal, market: PaperMarketState) -> bool:
        """Buy stops trigger at/above the stop; sell stops at/below."""
        return market.ask >= stop_price if side is Side.BUY else market.bid <= stop_price

    def evaluate(
        self,
        *,
        order_id: UUID,
        side: Side,
        order_type: OrderType,
        remaining_quantity: Decimal,
        limit_price: Decimal | None,
        stop_price: Decimal | None,
        stop_armed: bool,
        market: PaperMarketState,
        fill_round: int = 0,
    ) -> tuple[PaperFill | None, bool]:
        """Return (fill, stop_armed) for one tick of simulation."""
        if order_type in {OrderType.STOP, OrderType.STOP_LIMIT} and not stop_armed:
            if stop_price is None or not self.stop_triggered(
                side=side, stop_price=stop_price, market=market
            ):
                return None, False
            stop_armed = True

        effective_type = order_type
        if order_type is OrderType.STOP:
            effective_type = OrderType.MARKET
        elif order_type is OrderType.STOP_LIMIT:
            effective_type = OrderType.LIMIT

        if effective_type is OrderType.MARKET:
            return (
                self.fill_market_order(
                    order_id=order_id,
                    side=side,
                    remaining_quantity=remaining_quantity,
                    market=market,
                    fill_round=fill_round,
                ),
                stop_armed,
            )
        if limit_price is None:
            return None, stop_armed
        return (
            self.try_fill_limit_order(
                order_id=order_id,
                side=side,
                remaining_quantity=remaining_quantity,
                limit_price=limit_price,
                market=market,
            ),
            stop_armed,
        )
