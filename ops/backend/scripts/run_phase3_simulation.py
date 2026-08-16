"""Run a deterministic AWS-only Phase 3 end-to-end simulation.

This is a local/CI harness, not a production feature. It drives the existing
FastAPI routes in-process so the real authentication dependencies, ingestion
service, persistence layer, websocket broadcaster, EOD landing service,
dashboard read APIs and quant report generator are exercised together.

It deliberately refuses ``ENVIRONMENT=production`` and requires ``DATABASE_URL``:
the simulation writes synthetic fixture rows and raw EOD objects to the
configured ops database/storage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from app.api.dependencies.dashboard_auth import CREDENTIAL_SUBPROTOCOL
from app.core.config import Settings, get_settings
from app.database.session import database_enabled
from app.services.agent_service import machine_id_for
from fastapi.testclient import TestClient
from main import app

DEFAULT_MACHINE = "gcp-trading-01"
DEFAULT_AGENT_ID = "agent-phase3-sim"
DEFAULT_STRATEGY = "phase3-synthetic-observer"
DEFAULT_ACCOUNT = "paper-observation"


class SimulationError(RuntimeError):
    """The simulation cannot safely run with the current configuration."""


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.=-]+", "-", value.strip()).strip("-._")
    return cleaned[:80] or "phase3-sim"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _jsonl(rows: list[dict[str, Any]]) -> bytes:
    return ("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n").encode()


def _agent_token_for(settings: Settings, machine: str) -> str | None:
    explicit = os.environ.get("RAJ_SIM_AGENT_TOKEN")
    if explicit:
        return explicit
    if settings.raj_agent_token:
        return settings.raj_agent_token
    wanted = machine.strip().lower()
    for entry in (settings.raj_agent_tokens or "").split(","):
        scoped_machine, sep, token = entry.partition(":")
        if sep and scoped_machine.strip().lower() == wanted and token.strip():
            return token.strip()
    return None


def _dashboard_token_for(settings: Settings) -> str | None:
    return os.environ.get("RAJ_SIM_DASHBOARD_TOKEN") or settings.raj_dashboard_token


def _require_safe_configuration(settings: Settings, machine: str) -> tuple[str, str]:
    if settings.is_production:
        raise SimulationError(
            "refusing to run Phase 3 simulation with ENVIRONMENT=production; "
            "use a local/staging database instead"
        )
    if not database_enabled():
        raise SimulationError("DATABASE_URL is required for the durable Phase 3 simulation")
    agent_token = _agent_token_for(settings, machine)
    if not agent_token:
        raise SimulationError(
            "no usable agent token found; configure RAJ_SIM_AGENT_TOKEN, "
            "RAJ_AGENT_TOKEN, or a machine-scoped RAJ_AGENT_TOKENS entry"
        )
    dashboard_token = _dashboard_token_for(settings)
    if not dashboard_token:
        raise SimulationError(
            "RAJ_DASHBOARD_TOKEN or RAJ_SIM_DASHBOARD_TOKEN is required so the "
            "simulation can exercise authenticated dashboard REST/WebSocket reads"
        )
    return agent_token, dashboard_token


def _envelope(
    *,
    run_id: str,
    seq: int | None,
    kind: str,
    ts: str,
    machine: str,
    session_id: str,
    data: dict[str, Any],
    strategy: str = DEFAULT_STRATEGY,
) -> dict[str, Any]:
    suffix = f"s{seq:04d}" if seq is not None else "no-seq"
    return {
        "id": f"phase3-{run_id}-{suffix}-{kind}",
        "kind": kind,
        "machine": machine,
        "strategy": strategy,
        "account": DEFAULT_ACCOUNT,
        "session_id": session_id,
        "sequence_id": seq,
        "schema_version": 3,
        "ts": ts,
        "data": data,
    }


def _initial_offline_batch(
    *,
    run_id: str,
    machine: str,
    agent_id: str,
    session_id: str,
    stale_ts: str,
) -> dict[str, Any]:
    items = [
        _envelope(
            run_id=run_id,
            seq=1,
            kind="heartbeat",
            ts=stale_ts,
            machine=machine,
            session_id=session_id,
            data={
                "agentId": agent_id,
                "health": "healthy",
                "cpu": 38.5,
                "ram": 52.0,
                "disk": 61.2,
                "queueDepth": 6,
                "oldestPendingAgeSec": 540,
                "transportState": "disconnected",
                "currentSessionId": session_id,
                "tradingProcessState": "running",
            },
        ),
        _envelope(
            run_id=run_id,
            seq=2,
            kind="system_status",
            ts=stale_ts,
            machine=machine,
            session_id=session_id,
            data={
                "status": "offline",
                "queueDepth": 6,
                "oldestPendingAgeSec": 540,
                "transportState": "connection_lost",
                "tradingProcessState": "running",
                "message": "Synthetic Google agent connection lost",
            },
        ),
        _envelope(
            run_id=run_id,
            seq=3,
            kind="start",
            ts=stale_ts,
            machine=machine,
            session_id=session_id,
            data={"message": "Synthetic strategy lifecycle started", "symbol": "NIFTY"},
        ),
        _envelope(
            run_id=run_id,
            seq=4,
            kind="signal",
            ts=stale_ts,
            machine=machine,
            session_id=session_id,
            data={"status": "accepted", "symbol": "NIFTY", "side": "buy", "quantity": 1},
        ),
        _envelope(
            run_id=run_id,
            seq=5,
            kind="order",
            ts=stale_ts,
            machine=machine,
            session_id=session_id,
            data={"status": "submitted", "symbol": "NIFTY", "side": "buy", "quantity": 1},
        ),
        _envelope(
            run_id=run_id,
            seq=6,
            kind="fill",
            ts=stale_ts,
            machine=machine,
            session_id=session_id,
            data={"symbol": "NIFTY", "quantity": 1, "price": 100.0, "side": "buy"},
        ),
        _envelope(
            run_id=run_id,
            seq=7,
            kind="trade",
            ts=stale_ts,
            machine=machine,
            session_id=session_id,
            data={
                "symbol": "NIFTY",
                "direction": "long",
                "action": "close",
                "entry": 100.0,
                "exit": 104.0,
                "quantity": 1,
                "pnl": 4.0,
                "latencyMs": 31.0,
            },
        ),
        _envelope(
            run_id=run_id,
            seq=8,
            kind="pnl",
            ts=stale_ts,
            machine=machine,
            session_id=session_id,
            data={"symbol": "NIFTY", "pnl": 4.0, "realizedPnl": 4.0},
        ),
        _envelope(
            run_id=run_id,
            seq=9,
            kind="risk",
            ts=stale_ts,
            machine=machine,
            session_id=session_id,
            data={
                "severity": "warning",
                "reason": "synthetic exposure guard observed",
                "symbol": "NIFTY",
            },
        ),
        _envelope(
            run_id=run_id,
            seq=None,
            kind="unsupported_phase3_fixture",
            ts=stale_ts,
            machine=machine,
            session_id=session_id,
            data={"message": "intentional permanent rejection for dead-letter validation"},
        ),
    ]
    return {"agentId": agent_id, "machine": machine, "queueDepth": 6, "items": items}


def _recovery_gap_batch(
    *,
    run_id: str,
    machine: str,
    agent_id: str,
    session_id: str,
    now_ts: str,
) -> dict[str, Any]:
    # Sequence 10-11 are intentionally missing. This single-envelope batch makes
    # the gap visible without fabricating a failure in the ingestion service.
    return {
        "agentId": agent_id,
        "machine": machine,
        "queueDepth": 2,
        "items": [
            _envelope(
                run_id=run_id,
                seq=12,
                kind="recovery",
                ts=now_ts,
                machine=machine,
                session_id=session_id,
                data={
                    "status": "recovery_completed",
                    "state": "RECOVERY_COMPLETED",
                    "recoveryState": "recovering",
                    "eventsRecovered": 2,
                    "eodBacklog": 1,
                    "queueDepth": 2,
                    "message": "Synthetic replay drained after reconnect",
                },
            )
        ],
    }


def _final_online_batch(
    *,
    run_id: str,
    machine: str,
    agent_id: str,
    session_id: str,
    now_ts: str,
) -> dict[str, Any]:
    return {
        "agentId": agent_id,
        "machine": machine,
        "queueDepth": 0,
        "items": [
            _envelope(
                run_id=run_id,
                seq=13,
                kind="heartbeat",
                ts=now_ts,
                machine=machine,
                session_id=session_id,
                data={
                    "agentId": agent_id,
                    "health": "healthy",
                    "cpu": 29.0,
                    "ram": 47.0,
                    "disk": 61.3,
                    "queueDepth": 0,
                    "oldestPendingAgeSec": 0,
                    "transportState": "connected",
                    "currentSessionId": session_id,
                    "tradingProcessState": "running",
                    "lastEodStatus": "UPLOADING",
                },
            )
        ],
    }


def _online_recovery_state_batch(
    *,
    run_id: str,
    machine: str,
    agent_id: str,
    session_id: str,
    now_ts: str,
) -> dict[str, Any]:
    return {
        "agentId": agent_id,
        "machine": machine,
        "queueDepth": 0,
        "items": [
            _envelope(
                run_id=run_id,
                seq=14,
                kind="recovery",
                ts=now_ts,
                machine=machine,
                session_id=session_id,
                data={
                    "status": "online",
                    "state": "ONLINE",
                    "recoveryState": "online",
                    "eventsRecovered": 2,
                    "eodBacklog": 0,
                    "queueDepth": 0,
                    "message": "Synthetic Google agent fully online after recovery",
                },
            )
        ],
    }


def _eod_files(machine: str, session_id: str) -> tuple[bytes, bytes]:
    trades = _jsonl([
        {
            "time": "2026-08-10T09:20:00+05:30",
            "symbol": "NIFTY",
            "strategy": DEFAULT_STRATEGY,
            "session": session_id,
            "entry": 100.0,
            "exit": 104.0,
            "quantity": 1,
            "pnl": 4.0,
            "machine": machine,
        },
        {
            "time": "2026-08-10T10:15:00+05:30",
            "symbol": "NIFTY",
            "strategy": DEFAULT_STRATEGY,
            "session": session_id,
            "entry": 104.0,
            "exit": 101.0,
            "quantity": 1,
            "pnl": -3.0,
            "machine": machine,
        },
    ])
    candles = (
        b"time,symbol,close\n"
        b"2026-08-10T09:15:00+05:30,NIFTY,100\n"
        b"2026-08-10T09:16:00+05:30,NIFTY,102\n"
        b"2026-08-10T09:17:00+05:30,NIFTY,101\n"
        b"2026-08-10T09:18:00+05:30,NIFTY,105\n"
    )
    return trades, candles


def _manifest(dataset_id: str, machine: str, agent_id: str, session_id: str) -> dict[str, Any]:
    trades, candles = _eod_files(machine, session_id)
    return {
        "datasetId": dataset_id,
        "machine": machine,
        "agentId": agent_id,
        "sessionId": session_id,
        "tradingDate": "2026-08-10",
        "createdAt": "2026-08-10T16:05:00+05:30",
        "schemaVersion": "phase3-simulation-v1",
        "files": [
            {
                "fileId": "trades",
                "relativePath": "trades/executions.jsonl",
                "datasetType": "trades",
                "sizeBytes": len(trades),
                "sha256": _sha(trades),
                "rowCount": 2,
            },
            {
                "fileId": "candles",
                "relativePath": "candles/NIFTY.csv",
                "datasetType": "candles",
                "sizeBytes": len(candles),
                "sha256": _sha(candles),
                "rowCount": 4,
            },
        ],
    }


def _assert_ok(response, label: str) -> dict[str, Any]:
    if response.status_code >= 400:
        raise SimulationError(f"{label} failed: HTTP {response.status_code} {response.text}")
    try:
        return response.json()
    except Exception as exc:  # pragma: no cover - TestClient JSON decoding includes detail
        raise SimulationError(f"{label} did not return JSON: {response.text}") from exc


def _machine_row(summary: dict[str, Any], machine_id: str) -> dict[str, Any]:
    for row in summary.get("machines", []):
        if row.get("machineId") == machine_id:
            return row
    return {}


def run_simulation(*, seed: int, run_id: str, machine: str, agent_id: str) -> dict[str, Any]:
    settings = get_settings()
    agent_token, dashboard_token = _require_safe_configuration(settings, machine)
    run_id = _slug(run_id)
    session_id = f"phase3-sim-session-{run_id}"
    dataset_id = f"phase3-sim-eod-{run_id}"
    machine_id = machine_id_for(machine)

    now = datetime.now(UTC)
    stale = now - timedelta(seconds=settings.heartbeat_offline_after_seconds + 90)
    stale_ts = stale.isoformat()
    now_ts = now.isoformat()

    agent_headers = {
        "X-Raj-Agent-Token": agent_token,
        "X-Raj-Agent-Id": agent_id,
    }
    dashboard_headers = {"X-Raj-Dashboard-Token": dashboard_token}
    websocket_messages: list[dict[str, Any]] = []

    with TestClient(app) as client:
        with client.websocket_connect(
            "/api/ws",
            subprotocols=[CREDENTIAL_SUBPROTOCOL, dashboard_token],
        ) as websocket:
            websocket_messages.append(websocket.receive_json())

            initial_payload = _initial_offline_batch(
                run_id=run_id,
                machine=machine,
                agent_id=agent_id,
                session_id=session_id,
                stale_ts=stale_ts,
            )
            initial_ack = _assert_ok(
                client.post("/api/agent/batch", json=initial_payload, headers=agent_headers),
                "initial offline batch",
            )
            websocket_messages.extend(websocket.receive_json() for _ in range(3))

            offline_recovery = _assert_ok(
                client.get("/api/recovery/summary", headers=dashboard_headers),
                "offline recovery summary",
            )

            gap_ack = _assert_ok(
                client.post(
                    "/api/agent/batch",
                    json=_recovery_gap_batch(
                        run_id=run_id,
                        machine=machine,
                        agent_id=agent_id,
                        session_id=session_id,
                        now_ts=now_ts,
                    ),
                    headers=agent_headers,
                ),
                "recovery gap batch",
            )
            websocket_messages.append(websocket.receive_json())

            final_ack = _assert_ok(
                client.post(
                    "/api/agent/batch",
                    json=_final_online_batch(
                        run_id=run_id,
                        machine=machine,
                        agent_id=agent_id,
                        session_id=session_id,
                        now_ts=now_ts,
                    ),
                    headers=agent_headers,
                ),
                "final heartbeat batch",
            )
            websocket_messages.append(websocket.receive_json())

            online_state_ack = _assert_ok(
                client.post(
                    "/api/agent/batch",
                    json=_online_recovery_state_batch(
                        run_id=run_id,
                        machine=machine,
                        agent_id=agent_id,
                        session_id=session_id,
                        now_ts=now_ts,
                    ),
                    headers=agent_headers,
                ),
                "online recovery-state batch",
            )
            websocket_messages.append(websocket.receive_json())

            duplicate_items = initial_payload["items"][:2]
            duplicate_ack = _assert_ok(
                client.post(
                    "/api/agent/batch",
                    json={
                        "agentId": agent_id,
                        "machine": machine,
                        "queueDepth": 0,
                        "items": duplicate_items,
                    },
                    headers=agent_headers,
                ),
                "duplicate replay batch",
            )

        trades, candles = _eod_files(machine, session_id)
        manifest = _assert_ok(
            client.post(
                "/api/eod/manifests",
                json=_manifest(dataset_id, machine, agent_id, session_id),
                headers=agent_headers,
            ),
            "EOD manifest registration",
        )
        # Upload one file in two chunks to prove resumability and one in a single
        # chunk to keep the fixture small.
        split = len(trades) // 2
        eod_uploads = [
            _assert_ok(
                client.put(
                    f"/api/eod/datasets/{dataset_id}/files/trades/chunks?offset=0",
                    content=trades[:split],
                    headers=agent_headers,
                ),
                "EOD trades chunk 1",
            ),
            _assert_ok(
                client.put(
                    f"/api/eod/datasets/{dataset_id}/files/trades/chunks?offset={split}",
                    content=trades[split:],
                    headers=agent_headers,
                ),
                "EOD trades chunk 2",
            ),
            _assert_ok(
                client.put(
                    f"/api/eod/datasets/{dataset_id}/files/candles/chunks?offset=0",
                    content=candles,
                    headers=agent_headers,
                ),
                "EOD candles chunk",
            ),
        ]
        eod_complete = _assert_ok(
            client.post(f"/api/eod/datasets/{dataset_id}/complete", headers=agent_headers),
            "EOD completion",
        )
        eod_finalize = _assert_ok(
            client.post(f"/api/eod/datasets/{dataset_id}/finalize", headers=agent_headers),
            "EOD finalization",
        )
        online_recovery = _assert_ok(
            client.get("/api/recovery/summary", headers=dashboard_headers),
            "online recovery summary",
        )
        machine_view = _assert_ok(
            client.get(f"/api/machines/{machine_id}", headers=dashboard_headers),
            "machine detail",
        )
        event_timeline = _assert_ok(
            client.get(
                f"/api/events?machineId={machine_id}&sessionId={session_id}&limit=50",
                headers=dashboard_headers,
            ),
            "event timeline",
        )
        risk_events = _assert_ok(
            client.get(
                f"/api/events?machineId={machine_id}&eventType=risk&limit=10",
                headers=dashboard_headers,
            ),
            "event timeline risk filter",
        )
        eod_reconciliation = _assert_ok(
            client.get("/api/eod/reconciliation", headers=dashboard_headers),
            "EOD reconciliation",
        )
        quant_report = _assert_ok(
            client.get(f"/api/quant/datasets/{dataset_id}/report", headers=dashboard_headers),
            "quant dataset report",
        )

    offline_machine = _machine_row(offline_recovery, machine_id)
    online_machine = _machine_row(online_recovery, machine_id)
    from app.repositories import dead_letter_repo

    dead_letters = [
        row
        for row in dead_letter_repo.list()
        if str(row.get("envelopeId") or "").startswith(f"phase3-{run_id}-")
    ]
    return {
        "runId": run_id,
        "seed": seed,
        "machineId": machine_id,
        "machine": machine,
        "agentId": agent_id,
        "sessionId": session_id,
        "datasetId": dataset_id,
        "acks": {
            "initialOffline": initial_ack,
            "recoveryGap": gap_ack,
            "finalHeartbeat": final_ack,
            "onlineRecoveryState": online_state_ack,
            "duplicateReplay": duplicate_ack,
        },
        "websocket": {
            "authenticated": True,
            "observedMessages": len(websocket_messages),
            "messageTypes": [message.get("type") for message in websocket_messages],
        },
        "recovery": {
            "offlineStatus": offline_machine.get("status"),
            "offlineState": offline_machine.get("recoveryState"),
            "offlineDurationSec": offline_machine.get("offlineDurationSec"),
            "onlineStatus": online_machine.get("status"),
            "onlineState": online_machine.get("recoveryState"),
            "missingEvents": online_machine.get("missingEvents"),
            "gapCount": online_machine.get("gapCount"),
            "duplicateEvents": online_machine.get("duplicateEvents"),
        },
        "dashboard": {
            "machineStatus": machine_view.get("status"),
            "timelineEvents": len(event_timeline),
            "riskEvents": len(risk_events),
            "boundedPayloadPreview": all(
                "payload" not in row and len(str(row.get("payloadSummary") or "")) <= 240
                for row in event_timeline
            ),
        },
        "eod": {
            "manifestStatus": manifest.get("status"),
            "uploadStatuses": [upload.get("status") for upload in eod_uploads],
            "completeStatus": eod_complete.get("dataset", {}).get("status"),
            "finalStatus": eod_finalize.get("dataset", {}).get("status"),
            "checksumPassed": all(
                upload.get("checksumStatus") in {None, "PASSED"} for upload in eod_uploads
            ),
            "reconciliation": eod_reconciliation,
        },
        "quant": {
            "reportId": quant_report.get("reportId"),
            "status": quant_report.get("status"),
            "closedTrades": quant_report.get("tradeMetrics", {}).get("closedTrades"),
            "grossPnl": quant_report.get("tradeMetrics", {}).get("grossPnl"),
            "replayAvailable": quant_report.get("marketReplay", {}).get("available"),
            "points": len(quant_report.get("marketReplay", {}).get("points", [])),
        },
        "failureInjection": {
            "deadLetters": len(dead_letters),
            "duplicateReplaySafe": int(duplicate_ack.get("duplicate") or 0) == len(duplicate_items),
            "sequenceGapVisible": bool(gap_ack.get("sequenceGap")),
        },
        "authorityBoundary": {
            "awsToGoogleControlPath": False,
            "tradingControlsExercised": False,
            "brokerCallsExercised": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run deterministic AWS-only Phase 3 simulation.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--run-id",
        default=None,
        help="Deterministic fixture id. Defaults to a UTC timestamp suffix.",
    )
    parser.add_argument("--machine", default=os.environ.get("RAJ_SIM_MACHINE", DEFAULT_MACHINE))
    parser.add_argument("--agent-id", default=os.environ.get("RAJ_SIM_AGENT_ID", DEFAULT_AGENT_ID))
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON only.")
    args = parser.parse_args(argv)

    run_id = args.run_id or f"seed-{args.seed}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    try:
        summary = run_simulation(
            seed=args.seed,
            run_id=run_id,
            machine=args.machine,
            agent_id=args.agent_id,
        )
    except SimulationError as exc:
        print(f"Phase 3 simulation refused: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("Phase 3 AWS-only simulation complete")
        print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
