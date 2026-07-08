"""Secure broker-local execution agent.

Runs on a Windows/VPS host next to a broker terminal (notably MetaTrader 5),
exposing the HTTP contract the platform's MT5 execution adapter consumes:
``GET /health``, ``POST /orders``, ``POST /orders/{id}/cancel|replace``,
``GET /orders``, ``GET /account``, ``GET /positions``. Requests are
bearer-authenticated with the per-connection agent token.
"""

from algo_agent.plugins import BrokerPlugin, OrderRequest, SimulatorPlugin

__all__ = ["BrokerPlugin", "OrderRequest", "SimulatorPlugin"]
