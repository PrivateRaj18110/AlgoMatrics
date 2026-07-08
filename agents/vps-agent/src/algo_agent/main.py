"""Agent HTTP service.

Exposes the broker surface consumed by the platform's MT5 execution adapter,
authenticated with a bearer token (``AGENT_TOKEN``). The plugin is selected by
``AGENT_BROKER`` (``simulator`` by default; ``mt5`` on a Windows VPS).
"""

from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from algo_agent.plugins import BrokerPlugin, OrderRequest, SimulatorPlugin, order_payload


def build_plugin() -> BrokerPlugin:
    kind = os.environ.get("AGENT_BROKER", "simulator").lower()
    if kind == "mt5":  # pragma: no cover - Windows-only path
        from algo_agent.mt5 import Mt5Config, Mt5Plugin

        return Mt5Plugin(
            Mt5Config(
                login=int(os.environ["MT5_LOGIN"]),
                password=os.environ["MT5_PASSWORD"],
                server=os.environ["MT5_SERVER"],
                terminal_path=os.environ.get("MT5_TERMINAL_PATH"),
            )
        )
    return SimulatorPlugin()


def require_token(authorization: str = Header(default="")) -> None:
    expected = os.environ.get("AGENT_TOKEN", "")
    if not expected:
        environment = os.environ.get("AGENT_ENV", "local").lower()
        if environment not in {"local", "test"}:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="agent authentication is not configured",
            )
        return
    if authorization != f"Bearer {expected}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid agent token")


class SubmitOrderBody(BaseModel):
    client_order_id: str = Field(min_length=1, max_length=64)
    symbol: str = Field(min_length=1, max_length=40)
    side: str = Field(pattern="^(buy|sell)$")
    order_type: str = Field(pattern="^(market|limit|stop|stop_limit)$")
    volume: str
    limit_price: str | None = None
    stop_price: str | None = None


class ReplaceOrderBody(BaseModel):
    volume: str | None = None
    limit_price: str | None = None
    stop_price: str | None = None


def _decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation as error:
        raise HTTPException(status_code=422, detail=f"invalid decimal: {value}") from error


def create_app(plugin: BrokerPlugin | None = None) -> FastAPI:
    broker = plugin or build_plugin()
    app = FastAPI(title="Algo Matrics VPS Agent", version="0.1.0")

    @app.get("/health", dependencies=[Depends(require_token)])
    def health() -> dict[str, object]:
        return broker.health()

    @app.post("/orders", dependencies=[Depends(require_token)])
    def submit(body: SubmitOrderBody) -> dict[str, object]:
        volume = _decimal(body.volume) or Decimal("0")
        order = broker.submit(
            OrderRequest(
                client_order_id=body.client_order_id,
                symbol=body.symbol,
                side=body.side,
                order_type=body.order_type,
                volume=volume,
                limit_price=_decimal(body.limit_price),
                stop_price=_decimal(body.stop_price),
            )
        )
        return order_payload(order)

    @app.post("/orders/{order_id}/cancel", dependencies=[Depends(require_token)])
    def cancel(order_id: str) -> dict[str, object]:
        try:
            return order_payload(broker.cancel(order_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="order not found") from error

    @app.post("/orders/{order_id}/replace", dependencies=[Depends(require_token)])
    def replace(order_id: str, body: ReplaceOrderBody) -> dict[str, object]:
        try:
            return order_payload(
                broker.replace(
                    order_id,
                    volume=_decimal(body.volume),
                    limit_price=_decimal(body.limit_price),
                    stop_price=_decimal(body.stop_price),
                )
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="order not found") from error

    @app.get("/orders", dependencies=[Depends(require_token)])
    def orders() -> dict[str, object]:
        return {"orders": [order_payload(order) for order in broker.orders()]}

    @app.get("/account", dependencies=[Depends(require_token)])
    def account() -> dict[str, object]:
        return broker.account()

    @app.get("/positions", dependencies=[Depends(require_token)])
    def positions() -> dict[str, object]:
        return {"positions": broker.positions()}

    return app


app = create_app()


def main() -> None:  # pragma: no cover - process entrypoint
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("AGENT_PORT", "9100")))


if __name__ == "__main__":  # pragma: no cover
    main()
