"""Background mock-event publisher.

Mirrors the frontend's client-side engine: every few seconds it jitters machine
telemetry, emits a fresh system event and a connection heartbeat, then
broadcasts them to all websocket clients. This keeps the live feed "alive" even
before any real strategies are reporting in.
"""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timezone

from app.core.config import get_settings
from app.database.session import database_enabled
from app.realtime.broadcaster import broadcaster
from app.repositories import build_event, events_repo, machines_repo
from app.services.agent_service import LIVE_MACHINE_IDS

_rng = random.Random()

def _jitter(value: float, delta: float, lo: float, hi: float) -> float:
    return round(max(lo, min(hi, value + (_rng.random() - 0.5) * 2 * delta)))


def _age_seconds(iso_ts: str | None) -> float:
    if not iso_ts:
        return float("inf")
    try:
        ts = datetime.fromisoformat(iso_ts)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds()
    except ValueError:
        return float("inf")


async def publish_loop(interval: float = 3.0) -> None:
    """Run until cancelled, broadcasting mock telemetry + events.

    Live agent machines (tracked in ``LIVE_MACHINE_IDS``) are *not* jittered —
    their telemetry is driven by real heartbeats. They are only checked for
    staleness here so a crashed host flips to offline on the dashboard.
    """
    while True:
        try:
            await asyncio.sleep(interval)
            if broadcaster.client_count == 0:
                continue

            # The jitter + synthetic-event generation is a mock-layer feature.
            # In DB mode machines come from real heartbeats (staleness is derived
            # on read) so we neither jitter nor fabricate events — we just keep
            # broadcasting the live snapshot + connection heartbeat on the same
            # cadence and message types.
            mock_mode = not database_enabled()
            if mock_mode:
                # Mutating dicts returned by list() mutates the stored records.
                for m in machines_repo.list():
                    if m.get("id") in LIVE_MACHINE_IDS:
                        settings = get_settings()
                        age = _age_seconds(m.get("lastHeartbeat"))
                        if age > settings.heartbeat_offline_after_seconds:
                            m["status"] = "offline"
                            m["pythonStatus"] = "offline"
                            m["cpu"] = 0
                        elif age > settings.heartbeat_degraded_after_seconds:
                            m["status"] = "degraded"
                            m["pythonStatus"] = "degraded"
                        continue
                    if m["status"] == "offline":
                        continue
                    m["cpu"] = _jitter(m["cpu"], 6, 4, 99)
                    m["ram"] = _jitter(m["ram"], 3, 8, 98)
                    m["internetMs"] = _jitter(m["internetMs"], 4, 2, 240)
                    m["brokerPingMs"] = _jitter(m["brokerPingMs"], 5, 1, 280)
                    m["lastHeartbeat"] = datetime.now(timezone.utc).isoformat()

            await broadcaster.broadcast({"type": "machines", "payload": machines_repo.list()})
            await broadcaster.broadcast({
                "type": "connection",
                "payload": {
                    "latencyMs": 4 + round(_rng.random() * 22),
                    "time": datetime.now(timezone.utc).isoformat(),
                },
            })
            if mock_mode and _rng.random() < 0.6:
                event = build_event(0, f"evt-live-{datetime.now(timezone.utc).timestamp()}")
                events_repo.prepend(event)
                await broadcaster.broadcast({"type": "event", "payload": event})
        except asyncio.CancelledError:
            break
        except Exception:
            # Never let the publisher crash the app; keep looping.
            continue
