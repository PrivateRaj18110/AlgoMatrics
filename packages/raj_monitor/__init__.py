"""Raj Monitor — safe, production-grade strategy monitoring.

Architecture::

    Strategy -> monitor_sdk -> Local Agent -> FastAPI -> Supabase -> Dashboard

Two entry points:

* **Strategies** import the SDK singleton and call its stable methods::

      from raj_monitor import monitor
      monitor.start()
      monitor.trade(symbol="EURUSD", direction="long", action="open",
                    entry=1.0850, quantity=1.0)
      monitor.metric("sharpe", 1.84)
      monitor.event("Regime switched to trend", severity="info")
      monitor.stop()

  These methods are non-blocking and never raise into the strategy.

* **Operators** run one Local Agent per machine::

      python -m raj_monitor.agent --config config.yaml

The SDK talks ONLY to the Local Agent (localhost); the Agent is the only thing
that talks to the backend. This package is self-contained and installable
independently of the trading projects.
"""

from __future__ import annotations

from .constants import PROTOCOL_VERSION, SDK_VERSION
from .monitor_sdk import Monitor, monitor

__version__ = SDK_VERSION

__all__ = ["monitor", "Monitor", "run_agent", "SDK_VERSION", "PROTOCOL_VERSION", "__version__"]


def run_agent(config_path: str | None = None) -> int:
    """Convenience entry point to launch the Local Agent programmatically."""
    from .agent import main

    argv = ["--config", config_path] if config_path else []
    return main(argv)
