"""Derived offline/recovery status for the ops dashboard."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings
from app.repositories import eod_repo, machines_repo, sync_state_repo


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _age_seconds(value: str | None, now: datetime) -> int | None:
    parsed = _parse_time(value)
    if parsed is None:
        return None
    return max(0, int((now - parsed).total_seconds()))


def _derived_status(machine: dict[str, Any], heartbeat_age: int | None) -> str:
    status = str(machine.get("status") or "unknown").lower()
    # SQL rows are already derived by repositories.sql. Mock-mode live rows need
    # the same derivation so tests/dev don't display stale online machines.
    if not machine.get("live"):
        return status if status in {"online", "degraded", "offline", "unknown"} else "unknown"
    if heartbeat_age is None:
        return "unknown"
    settings = get_settings()
    if heartbeat_age > settings.heartbeat_offline_after_seconds:
        return "offline"
    if heartbeat_age > settings.heartbeat_degraded_after_seconds:
        return "degraded"
    return status if status in {"online", "degraded", "offline", "unknown"} else "online"


def _eod_backlog(machine_id: str) -> int:
    try:
        rows = eod_repo.list(limit=500, machine_id=machine_id)
    except Exception:
        return 0
    return sum(1 for row in rows if row.get("status") != "COMPLETE")


def _sync_by_machine() -> dict[str, dict[str, Any]]:
    try:
        rows = sync_state_repo.list()
    except Exception:
        return {}
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        mid = row.get("machineId")
        if not mid:
            continue
        current = merged.setdefault(
            mid,
            {
                "acceptedCount": 0,
                "duplicateCount": 0,
                "failedCount": 0,
                "missingCount": 0,
                "gapCount": 0,
                "queueDepth": None,
                "lastGapAt": None,
            },
        )
        for key in ("acceptedCount", "duplicateCount", "failedCount", "missingCount", "gapCount"):
            current[key] += int(row.get(key) or 0)
        if row.get("queueDepth") is not None:
            current["queueDepth"] = row["queueDepth"]
        if row.get("lastGapAt") and str(row["lastGapAt"]) > str(current.get("lastGapAt") or ""):
            current["lastGapAt"] = row["lastGapAt"]
    return merged


def _recovery_state(machine: dict[str, Any], status: str, queue_depth: int | None) -> str:
    raw = str(machine.get("recoveryState") or machine.get("transportState") or "").lower()
    if "recover" in raw or raw in {"draining", "replaying", "resyncing"}:
        return "recovering"
    if status in {"offline", "degraded", "unknown"}:
        return status
    if queue_depth and queue_depth > 0:
        return "recovering"
    return "online"


def _warnings(
    machine: dict[str, Any],
    status: str,
    sync: dict[str, Any],
    eod_backlog: int,
) -> list[str]:
    warnings: list[str] = []
    if status == "offline":
        warnings.append("heartbeat is beyond offline threshold")
    elif status == "degraded":
        warnings.append("heartbeat is beyond degraded threshold")
    if int(sync.get("missingCount") or 0) > 0:
        warnings.append("sequence gaps detected")
    if eod_backlog > 0:
        warnings.append("EOD datasets are not finalized")
    if int(sync.get("failedCount") or 0) > 0:
        warnings.append("telemetry failures recorded")
    return warnings


def summary() -> dict[str, Any]:
    now = _now()
    settings = get_settings()
    sync_rows = _sync_by_machine()
    machines: list[dict[str, Any]] = []
    for machine in machines_repo.list():
        machine_id = str(machine["id"])
        sync = sync_rows.get(machine_id, {})
        heartbeat_age = _age_seconds(machine.get("lastHeartbeat"), now)
        status = _derived_status(machine, heartbeat_age)
        queue_depth = machine.get("queueDepth")
        if queue_depth is None:
            queue_depth = sync.get("queueDepth")
        eod_backlog = int(machine.get("eodBacklog") or _eod_backlog(machine_id))
        offline_duration = None
        if status == "offline" and heartbeat_age is not None:
            offline_duration = max(0, int(heartbeat_age - settings.heartbeat_offline_after_seconds))
        recovery_state = _recovery_state(machine, status, queue_depth)
        row = {
            "machineId": machine_id,
            "machine": machine.get("name") or machine_id,
            "status": status,
            "recoveryState": recovery_state,
            "lastHeartbeat": machine.get("lastHeartbeat") or None,
            "heartbeatAgeSec": heartbeat_age,
            "offlineDurationSec": offline_duration,
            "queueDepth": queue_depth,
            "oldestPendingAgeSec": machine.get("oldestPendingAgeSec"),
            "transportState": machine.get("transportState"),
            "currentSessionId": machine.get("currentSessionId"),
            "tradingProcessState": machine.get("tradingProcessState"),
            "lastEodSync": machine.get("lastEodSync") or None,
            "lastEodStatus": machine.get("lastEodStatus"),
            "eodBacklog": eod_backlog,
            "eventsRecovered": int(
                machine.get("eventsRecovered") or sync.get("acceptedCount") or 0
            ),
            "acceptedEvents": int(sync.get("acceptedCount") or 0),
            "duplicateEvents": int(sync.get("duplicateCount") or 0),
            "failedEvents": int(sync.get("failedCount") or 0),
            "missingEvents": int(sync.get("missingCount") or 0),
            "gapCount": int(sync.get("gapCount") or 0),
            "lastGapAt": sync.get("lastGapAt") or None,
            "lastRecovery": machine.get("lastRecovery") or None,
            "warnings": _warnings(machine, status, sync, eod_backlog),
        }
        machines.append(row)

    return {
        "generatedAt": now.isoformat(),
        "totalMachines": len(machines),
        "online": sum(1 for m in machines if m["status"] == "online"),
        "degraded": sum(1 for m in machines if m["status"] == "degraded"),
        "offline": sum(1 for m in machines if m["status"] == "offline"),
        "unknown": sum(1 for m in machines if m["status"] == "unknown"),
        "recovering": sum(1 for m in machines if m["recoveryState"] == "recovering"),
        "totalQueueDepth": sum(int(m.get("queueDepth") or 0) for m in machines),
        "totalEodBacklog": sum(int(m.get("eodBacklog") or 0) for m in machines),
        "totalMissingEvents": sum(int(m.get("missingEvents") or 0) for m in machines),
        "machines": machines,
    }
