"""Strategy identity from Google telemetry (no dimension table).

Rule
----
``strategy_id = "{machine_id}::{strategy_name}"``

- ``strategy_name`` is the exact string on the envelope / ``strategy_status`` /
  trade payload. Never a hardcoded catalog name.
- ``machine_id`` is the telemetry host id (``mch-agent-…``). Missing machine
  uses the literal ``unknown``.
- The same name on two machines is two strategies.
- Repeated events for the same pair do not create duplicates.
"""

from __future__ import annotations


def strategy_identity(name: str | None, machine_id: str | None) -> str:
    clean = (name or "").strip()
    if not clean:
        return ""
    host = (machine_id or "").strip() or "unknown"
    return f"{host}::{clean}"
