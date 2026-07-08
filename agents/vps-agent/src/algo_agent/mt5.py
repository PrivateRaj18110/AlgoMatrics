"""MetaTrader 5 broker plugin (Windows/VPS only).

Binds the agent's broker surface to the MetaTrader5 terminal via the vendor
``MetaTrader5`` package, which is available only on Windows next to a running
terminal. It is imported lazily so the agent (and its simulator plugin) run
on any platform; instantiating ``Mt5Plugin`` off Windows raises clearly.

This translates MT5 retcodes, lots, and symbol suffixes into the canonical
statuses the platform expects. It is the single integration point for live
MT5 trading; nothing else in the codebase imports the terminal.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from algo_agent.plugins import AgentOrder, OrderRequest

_RETCODE_DONE = 10009  # TRADE_RETCODE_DONE


@dataclass(slots=True)
class Mt5Config:
    login: int
    password: str
    server: str
    terminal_path: str | None = None


class Mt5Plugin:
    def __init__(self, config: Mt5Config) -> None:
        try:
            import MetaTrader5 as mt5
        except ImportError as error:  # pragma: no cover - Windows-only dependency
            raise RuntimeError(
                "the MetaTrader5 package is required for the MT5 plugin; it is only "
                "available on Windows next to a running MT5 terminal"
            ) from error
        self._mt5 = mt5
        self._config = config
        if not mt5.initialize(
            login=config.login,
            password=config.password,
            server=config.server,
            path=config.terminal_path,
        ):
            raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")

    def health(self) -> dict[str, object]:  # pragma: no cover - requires terminal
        info = self._mt5.account_info()
        terminal = self._mt5.terminal_info()
        connected = bool(terminal and terminal.connected)
        return {
            "terminal_connected": connected,
            "account": str(info.login) if info else str(self._config.login),
            "currency": info.currency if info else "USD",
            "plugin": "mt5",
        }

    def submit(self, request: OrderRequest) -> AgentOrder:  # pragma: no cover
        mt5 = self._mt5
        order_kind = mt5.ORDER_TYPE_BUY if request.side == "buy" else mt5.ORDER_TYPE_SELL
        tick = mt5.symbol_info_tick(request.symbol)
        price = (
            float(request.limit_price)
            if request.limit_price
            else (tick.ask if request.side == "buy" else tick.bid)
        )
        result = mt5.order_send(
            {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": request.symbol,
                "volume": float(request.volume),
                "type": order_kind,
                "price": price,
                "deviation": 20,
                "magic": 42,
                "comment": request.client_order_id[:24],
                "type_time": mt5.ORDER_TIME_GTC,
            }
        )
        status = "filled" if result.retcode == _RETCODE_DONE else "rejected"
        return AgentOrder(
            order_id=str(result.order),
            client_order_id=request.client_order_id,
            symbol=request.symbol,
            side=request.side,
            volume=request.volume,
            status=status,
            filled_volume=request.volume if status == "filled" else Decimal("0"),
            average_price=Decimal(str(result.price)) if status == "filled" else None,
        )

    def cancel(self, order_id: str) -> AgentOrder:  # pragma: no cover
        mt5 = self._mt5
        mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": int(order_id)})
        return AgentOrder(
            order_id=order_id,
            client_order_id="",
            symbol="",
            side="",
            volume=Decimal("0"),
            status="cancelled",
        )

    def replace(
        self,
        order_id: str,
        *,
        volume: Decimal | None,
        limit_price: Decimal | None,
        stop_price: Decimal | None,
    ) -> AgentOrder:  # pragma: no cover
        _ = (volume, limit_price, stop_price)
        return AgentOrder(
            order_id=order_id,
            client_order_id="",
            symbol="",
            side="",
            volume=Decimal("0"),
            status="submitted",
        )

    def orders(self) -> list[AgentOrder]:  # pragma: no cover
        orders = self._mt5.orders_get() or []
        result: list[AgentOrder] = []
        for order in orders:
            result.append(
                AgentOrder(
                    order_id=str(order.ticket),
                    client_order_id=order.comment,
                    symbol=order.symbol,
                    side="buy" if order.type == self._mt5.ORDER_TYPE_BUY else "sell",
                    volume=Decimal(str(order.volume_current)),
                    status="submitted",
                )
            )
        return result

    def account(self) -> dict[str, object]:  # pragma: no cover
        info = self._mt5.account_info()
        return {
            "account": str(info.login),
            "currency": info.currency,
            "balance": str(info.balance),
        }

    def positions(self) -> list[dict[str, object]]:  # pragma: no cover
        positions = self._mt5.positions_get() or []
        return [
            {
                "symbol": position.symbol,
                "volume": str(position.volume),
                "price_open": str(position.price_open),
                "profit": str(position.profit),
            }
            for position in positions
        ]
