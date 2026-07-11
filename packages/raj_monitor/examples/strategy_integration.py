"""Example: wiring raj_monitor into a trading strategy.

This is the *entire* integration surface. Copy the raj_monitor package into your
strategy project (or `pip install ./raj_monitor`), set a few environment
variables, and add the calls below. The SDK is non-blocking and fail-safe, so
none of these calls can slow down or crash your trading loop.

Run a Local Agent on the same machine first:

    python -m raj_monitor.agent --config config.yaml

Then run this strategy with the matching identity:

    RAJ_STRATEGY=MR-FX RAJ_MACHINE="London VPS" RAJ_LOCAL_TOKEN=... python strategy_integration.py
"""

from __future__ import annotations

import random
import time
import traceback

from raj_monitor import monitor


def fake_signal() -> dict | None:
    if random.random() < 0.3:
        side = random.choice(["long", "short"])
        return {"symbol": "EURUSD", "side": side, "price": round(1.08 + random.uniform(-0.01, 0.01), 5)}
    return None


def main() -> None:
    # 1) Announce the strategy is up (optionally pass metadata).
    monitor.start(version="1.4.0", broker="IC Markets", symbols=["EURUSD", "GBPUSD"])

    open_trade: dict | None = None
    try:
        for _ in range(20):  # a real strategy loops forever
            # 2) Optional: a manual heartbeat / custom metric.
            monitor.metric("equity", round(10_000 + random.uniform(-500, 1500), 2), unit="USD")

            signal = fake_signal()
            if signal and open_trade is None:
                # 3) Trade opened.
                monitor.trade(symbol=signal["symbol"], direction=signal["side"],
                              action="open", entry=signal["price"], quantity=1.0)
                monitor.position(symbol=signal["symbol"], direction=signal["side"],
                                 quantity=1.0, entry=signal["price"], unrealized_pnl=0.0)
                open_trade = signal
            elif open_trade is not None and random.random() < 0.5:
                # 4) Trade closed.
                pnl = round(random.uniform(-200, 400), 2)
                monitor.trade(symbol=open_trade["symbol"], direction=open_trade["side"],
                              action="close", entry=open_trade["price"],
                              exit=open_trade["price"] + random.uniform(-0.002, 0.002),
                              quantity=1.0, pnl=pnl)
                monitor.event(f"Closed {open_trade['symbol']} for {pnl:+.0f}",
                              severity="info" if pnl >= 0 else "warning")
                open_trade = None

            monitor.log("loop tick complete", level="debug")
            time.sleep(0.5)
    except Exception:
        # 5) Any crash is reported as a critical event (then re-raised).
        monitor.error("Strategy crashed", traceback=traceback.format_exc())
        raise
    finally:
        # 6) Clean shutdown flushes a final 'stopped' event.
        monitor.stop()


if __name__ == "__main__":
    main()
