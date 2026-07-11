"""Example / test harness: simulate a fleet of machines + strategies.

Spins up several Local Agents (one per simulated machine, each on its own local
port) and drives random trading activity into them via the SDK protocol. Useful
for exercising the milestone's testing matrix — multiple strategies, three
machines simultaneously, backend restarts, internet loss.

Start the backend first (``cd backend && uvicorn main:app --reload``), then:

    python raj_monitor/examples/simulate_fleet.py --backend http://127.0.0.1:8000/api

Watch the dashboard (with VITE_USE_MOCK=false) light up with three live machines.
Ctrl+C to stop.
"""

from __future__ import annotations

import argparse
import json
import random
import threading
import time
import urllib.request

from raj_monitor.agent import Agent
from raj_monitor.config import Config
from raj_monitor.types import Envelope

MACHINES = [
    ("London VPS", 8771, ["MR-FX", "MOM", "XAU-SC"]),
    ("Google Cloud", 8772, ["CT", "IDX-ON"]),
    ("Personal Computer", 8773, ["GRID"]),
]
SYMBOLS = ["EURUSD", "GBPUSD", "XAUUSD", "BTCUSD", "US500"]


def _post(port: int, kind: str, strategy: str, machine: str, data: dict) -> None:
    env = Envelope(kind=kind, data=data, strategy=strategy, machine=machine).as_dict()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/ingest",
        data=json.dumps(env).encode(), headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=2).read()
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="http://127.0.0.1:8000/api")
    parser.add_argument("--queue-dir", default=".")
    args = parser.parse_args()

    agents: list[Agent] = []
    for name, port, _ in MACHINES:
        cfg = Config(
            machine_name=name, agent_port=port, backend_url=args.backend,
            queue_db=f"{args.queue_dir}/queue_{port}.db", log_dir="",
            heartbeat_sec=5, metrics_sec=10, upload_sec=2,
        )
        agent = Agent(cfg)
        threading.Thread(target=agent.run, daemon=True).start()
        agents.append(agent)
        print(f"agent up: {name} on :{port}")
    time.sleep(1.5)

    print("driving activity (Ctrl+C to stop)...")
    try:
        while True:
            name, port, strategies = random.choice(MACHINES)
            strategy = random.choice(strategies)
            sym = random.choice(SYMBOLS)
            roll = random.random()
            if roll < 0.5:
                _post(port, "trade", strategy, name, {
                    "symbol": sym, "action": random.choice(["open", "close"]),
                    "direction": random.choice(["long", "short"]),
                    "entry": round(random.uniform(1, 2000), 3),
                    "quantity": 1.0, "pnl": round(random.uniform(-400, 700), 0),
                })
            elif roll < 0.8:
                _post(port, "event", strategy, name, {
                    "message": f"{strategy}: {sym} regime change", "category": "strategy",
                    "severity": random.choice(["info", "info", "warning"]),
                })
            else:
                _post(port, "metric", strategy, name, {
                    "name": "sharpe", "value": round(random.uniform(0.5, 2.5), 2), "unit": None,
                })
            time.sleep(random.uniform(0.3, 1.2))
    except KeyboardInterrupt:
        print("\nstopping agents...")
        for agent in agents:
            agent.shutdown()


if __name__ == "__main__":
    main()
