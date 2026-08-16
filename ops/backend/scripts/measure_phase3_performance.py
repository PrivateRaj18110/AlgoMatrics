"""Measure Phase 3 AWS-side local performance.

This script is a reproducible local/staging harness for the acceptance report.
It drives the existing FastAPI app in-process against the configured database
and EOD storage, then emits JSON timing measurements for ingestion, websocket
broadcast, dashboard reads, EOD landing/finalization and quant report reads.

It is not a production load test and deliberately refuses production
environments. Use it to generate comparable smoke numbers before the final
Google <-> AWS integration phase.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import sys
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from app.api.dependencies.dashboard_auth import CREDENTIAL_SUBPROTOCOL
from app.core.config import Settings, get_settings
from app.database.session import database_enabled
from app.services.agent_service import machine_id_for
from fastapi.testclient import TestClient
from main import app

DEFAULT_MACHINE = "gcp-trading-01"
DEFAULT_AGENT_ID = "agent-phase3-perf"
DEFAULT_STRATEGY = "phase3-performance-probe"


class PerformanceMeasureError(RuntimeError):
    """The performance harness cannot safely run."""


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.=-]+", "-", value.strip()).strip("-._")
    return cleaned[:80] or "phase3-perf"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _jsonl(rows: list[dict[str, Any]]) -> bytes:
    return ("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n").encode()


def _agent_token_for(settings: Settings, machine: str) -> str | None:
    explicit = os.environ.get("RAJ_PERF_AGENT_TOKEN")
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
    return os.environ.get("RAJ_PERF_DASHBOARD_TOKEN") or settings.raj_dashboard_token


def _require_safe_configuration(settings: Settings, machine: str) -> tuple[str, str]:
    if settings.is_production:
        raise PerformanceMeasureError(
            "refusing to run Phase 3 performance measurement with ENVIRONMENT=production"
        )
    if not database_enabled():
        raise PerformanceMeasureError("DATABASE_URL is required for performance measurement")
    agent_token = _agent_token_for(settings, machine)
    if not agent_token:
        raise PerformanceMeasureError(
            "no usable agent token found; configure RAJ_PERF_AGENT_TOKEN, "
            "RAJ_AGENT_TOKEN, or a machine-scoped RAJ_AGENT_TOKENS entry"
        )
    dashboard_token = _dashboard_token_for(settings)
    if not dashboard_token:
        raise PerformanceMeasureError(
            "RAJ_DASHBOARD_TOKEN or RAJ_PERF_DASHBOARD_TOKEN is required"
        )
    return agent_token, dashboard_token


def _ms(seconds: float) -> float:
    return round(seconds * 1000.0, 3)


def _p50(values: list[float]) -> float:
    return round(statistics.median(values), 3) if values else 0.0


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * 0.95))
    return round(ordered[index], 3)


def _assert_ok(response, label: str) -> dict[str, Any]:
    if response.status_code >= 400:
        raise PerformanceMeasureError(
            f"{label} failed: HTTP {response.status_code} {response.text}"
        )
    return response.json()


def _register_machine(
    client: TestClient,
    *,
    headers: dict[str, str],
    machine: str,
    agent_id: str,
    run_id: str,
) -> float:
    start = perf_counter()
    _assert_ok(
        client.post(
            "/api/agent/register",
            json={
                "agentId": agent_id,
                "machine": machine,
                "location": "Phase 3 local performance harness",
                "provider": "Synthetic Google Agent",
                "sdkVersion": f"phase3-perf-{run_id}",
                "python": "local",
                "hostname": machine,
                "environment": "performance",
            },
            headers=headers,
        ),
        "agent register",
    )
    return _ms(perf_counter() - start)


def _event_item(
    *,
    run_id: str,
    index: int,
    machine: str,
    session_id: str,
) -> dict[str, Any]:
    return {
        "id": f"phase3-perf-{run_id}-evt-{index:06d}",
        "kind": "event",
        "machine": machine,
        "strategy": DEFAULT_STRATEGY,
        "session_id": session_id,
        "sequence_id": index,
        "schema_version": 3,
        "ts": _now_iso(),
        "data": {
            "category": "strategy",
            "severity": "info",
            "type": "performance_probe",
            "symbol": "NIFTY",
            "message": f"performance probe {index}",
        },
    }


def _measure_ingest(
    client: TestClient,
    *,
    headers: dict[str, str],
    run_id: str,
    machine: str,
    agent_id: str,
    session_id: str,
    batches: int,
    batch_size: int,
) -> dict[str, Any]:
    latencies: list[float] = []
    accepted = 0
    total = 0
    first_batch: dict[str, Any] | None = None
    first_index = 1
    overall_start = perf_counter()
    for batch_index in range(batches):
        start_index = first_index + (batch_index * batch_size)
        items = [
            _event_item(
                run_id=run_id,
                index=start_index + offset,
                machine=machine,
                session_id=session_id,
            )
            for offset in range(batch_size)
        ]
        payload = {"agentId": agent_id, "machine": machine, "queueDepth": 0, "items": items}
        if first_batch is None:
            first_batch = payload
        start = perf_counter()
        body = _assert_ok(
            client.post("/api/agent/batch", json=payload, headers=headers),
            f"ingest batch {batch_index + 1}",
        )
        latencies.append(_ms(perf_counter() - start))
        accepted += int(body.get("processed") or 0)
        total += int(body.get("total") or 0)
    elapsed = perf_counter() - overall_start

    duplicate_latency_ms = 0.0
    duplicate_count = 0
    if first_batch is not None:
        start = perf_counter()
        duplicate = _assert_ok(
            client.post("/api/agent/batch", json=first_batch, headers=headers),
            "duplicate replay batch",
        )
        duplicate_latency_ms = _ms(perf_counter() - start)
        duplicate_count = int(duplicate.get("duplicate") or 0)

    return {
        "batches": batches,
        "batchSize": batch_size,
        "submitted": total,
        "accepted": accepted,
        "elapsedMs": _ms(elapsed),
        "throughputEnvelopesPerSec": round(accepted / elapsed if elapsed > 0 else 0.0, 3),
        "requestLatencyMs": {
            "p50": _p50(latencies),
            "p95": _p95(latencies),
            "max": round(max(latencies) if latencies else 0.0, 3),
            "samples": latencies,
        },
        "writeLatencyMsPerEnvelope": round(sum(latencies) / accepted if accepted else 0.0, 6),
        "duplicateReplay": {
            "duplicates": duplicate_count,
            "latencyMs": duplicate_latency_ms,
        },
    }


def _measure_websocket(
    client: TestClient,
    *,
    dashboard_token: str,
    agent_headers: dict[str, str],
    run_id: str,
    machine: str,
    session_id: str,
) -> dict[str, Any]:
    item = _event_item(run_id=run_id, index=900_000, machine=machine, session_id=session_id)
    with client.websocket_connect(
        "/api/ws",
        subprotocols=[CREDENTIAL_SUBPROTOCOL, dashboard_token],
    ) as websocket:
        initial = websocket.receive_json()
        start = perf_counter()
        _assert_ok(
            client.post(
                "/api/agent/batch",
                json={
                    "agentId": DEFAULT_AGENT_ID,
                    "machine": machine,
                    "queueDepth": 0,
                    "items": [item],
                },
                headers=agent_headers,
            ),
            "websocket probe batch",
        )
        notification = websocket.receive_json()
        latency_ms = _ms(perf_counter() - start)
    return {
        "authenticated": True,
        "initialType": initial.get("type"),
        "notificationType": notification.get("type"),
        "latencyMs": latency_ms,
    }


def _timed_get(client: TestClient, url: str, headers: dict[str, str], label: str) -> dict[str, Any]:
    start = perf_counter()
    body = _assert_ok(client.get(url, headers=headers), label)
    return {
        "latencyMs": _ms(perf_counter() - start),
        "rows": len(body) if isinstance(body, list) else None,
    }


def _eod_payloads(session_id: str) -> tuple[bytes, bytes]:
    trades = _jsonl([
        {
            "time": "2026-08-10T09:20:00+05:30",
            "symbol": "NIFTY",
            "strategy": DEFAULT_STRATEGY,
            "session": session_id,
            "pnl": 5.0,
        },
        {
            "time": "2026-08-10T10:10:00+05:30",
            "symbol": "NIFTY",
            "strategy": DEFAULT_STRATEGY,
            "session": session_id,
            "pnl": -2.0,
        },
    ])
    candles = (
        b"time,symbol,close\n"
        b"2026-08-10T09:15:00+05:30,NIFTY,100\n"
        b"2026-08-10T09:16:00+05:30,NIFTY,101\n"
        b"2026-08-10T09:17:00+05:30,NIFTY,103\n"
        b"2026-08-10T09:18:00+05:30,NIFTY,102\n"
    )
    return trades, candles


def _measure_eod_quant(
    client: TestClient,
    *,
    headers: dict[str, str],
    dashboard_headers: dict[str, str],
    run_id: str,
    machine: str,
    agent_id: str,
    session_id: str,
) -> dict[str, Any]:
    dataset_id = f"phase3-perf-eod-{run_id}"
    trades, candles = _eod_payloads(session_id)
    manifest = {
        "datasetId": dataset_id,
        "machine": machine,
        "agentId": agent_id,
        "sessionId": session_id,
        "tradingDate": "2026-08-10",
        "createdAt": "2026-08-10T16:05:00+05:30",
        "schemaVersion": "phase3-performance-v1",
        "files": [
            {
                "fileId": "trades",
                "relativePath": "trades/perf.jsonl",
                "datasetType": "trades",
                "sizeBytes": len(trades),
                "sha256": _sha(trades),
                "rowCount": 2,
            },
            {
                "fileId": "candles",
                "relativePath": "candles/perf.csv",
                "datasetType": "candles",
                "sizeBytes": len(candles),
                "sha256": _sha(candles),
                "rowCount": 4,
            },
        ],
    }
    start = perf_counter()
    _assert_ok(client.post("/api/eod/manifests", json=manifest, headers=headers), "EOD manifest")
    manifest_ms = _ms(perf_counter() - start)

    upload_start = perf_counter()
    for file_id, payload in (("trades", trades), ("candles", candles)):
        _assert_ok(
            client.put(
                f"/api/eod/datasets/{dataset_id}/files/{file_id}/chunks?offset=0",
                content=payload,
                headers=headers,
            ),
            f"EOD upload {file_id}",
        )
    upload_ms = _ms(perf_counter() - upload_start)

    start = perf_counter()
    complete = _assert_ok(
        client.post(f"/api/eod/datasets/{dataset_id}/complete", headers=headers),
        "EOD complete",
    )
    complete_ms = _ms(perf_counter() - start)

    start = perf_counter()
    finalize = _assert_ok(
        client.post(f"/api/eod/datasets/{dataset_id}/finalize", headers=headers),
        "EOD finalize",
    )
    finalize_ms = _ms(perf_counter() - start)

    start = perf_counter()
    report = _assert_ok(
        client.get(f"/api/quant/datasets/{dataset_id}/report", headers=dashboard_headers),
        "quant report read",
    )
    report_read_ms = _ms(perf_counter() - start)

    return {
        "datasetId": dataset_id,
        "manifestLatencyMs": manifest_ms,
        "uploadLatencyMs": upload_ms,
        "completeLatencyMs": complete_ms,
        "finalizeAndAnalyzeLatencyMs": finalize_ms,
        "quantReportReadLatencyMs": report_read_ms,
        "finalStatus": finalize.get("dataset", {}).get("status"),
        "completeStatus": complete.get("dataset", {}).get("status"),
        "quantStatus": report.get("status"),
        "quantClosedTrades": report.get("tradeMetrics", {}).get("closedTrades"),
        "quantReplayAvailable": report.get("marketReplay", {}).get("available"),
    }


def measure_performance(
    *,
    run_id: str,
    machine: str,
    agent_id: str,
    batches: int,
    batch_size: int,
) -> dict[str, Any]:
    settings = get_settings()
    agent_token, dashboard_token = _require_safe_configuration(settings, machine)
    run_id = _slug(run_id)
    session_id = f"phase3-perf-session-{run_id}"
    machine_id = machine_id_for(machine)
    agent_headers = {"X-Raj-Agent-Token": agent_token, "X-Raj-Agent-Id": agent_id}
    dashboard_headers = {"X-Raj-Dashboard-Token": dashboard_token}

    with TestClient(app) as client:
        register_ms = _register_machine(
            client,
            headers=agent_headers,
            machine=machine,
            agent_id=agent_id,
            run_id=run_id,
        )
        ingest = _measure_ingest(
            client,
            headers=agent_headers,
            run_id=run_id,
            machine=machine,
            agent_id=agent_id,
            session_id=session_id,
            batches=batches,
            batch_size=batch_size,
        )
        websocket = _measure_websocket(
            client,
            dashboard_token=dashboard_token,
            agent_headers=agent_headers,
            run_id=run_id,
            machine=machine,
            session_id=session_id,
        )
        dashboard_reads = {
            "machines": _timed_get(client, "/api/machines", dashboard_headers, "machines read"),
            "events": _timed_get(
                client,
                f"/api/events?machineId={machine_id}&sessionId={session_id}&limit=100",
                dashboard_headers,
                "events read",
            ),
            "recovery": _timed_get(
                client,
                "/api/recovery/summary",
                dashboard_headers,
                "recovery read",
            ),
        }
        eod_quant = _measure_eod_quant(
            client,
            headers=agent_headers,
            dashboard_headers=dashboard_headers,
            run_id=run_id,
            machine=machine,
            agent_id=agent_id,
            session_id=session_id,
        )

    return {
        "runId": run_id,
        "generatedAt": _now_iso(),
        "machineId": machine_id,
        "machine": machine,
        "agentId": agent_id,
        "sessionId": session_id,
        "environment": {
            "database": "configured",
            "eodStorageBackend": settings.eod_storage_backend,
            "production": settings.is_production,
        },
        "measurements": {
            "agentRegisterLatencyMs": register_ms,
            "ingestion": ingest,
            "websocketBroadcast": websocket,
            "dashboardReads": dashboard_reads,
            "eodAndQuant": eod_quant,
        },
        "notes": [
            "local/staging TestClient measurement, not a production load test",
            "AWS-side only; no Google VM, broker, execution or strategy-control calls",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure Phase 3 AWS-side local performance.")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--machine", default=os.environ.get("RAJ_PERF_MACHINE", DEFAULT_MACHINE))
    parser.add_argument("--agent-id", default=os.environ.get("RAJ_PERF_AGENT_ID", DEFAULT_AGENT_ID))
    parser.add_argument("--batches", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.batches < 1 or args.batch_size < 1:
        print("batches and batch-size must be positive", file=sys.stderr)
        return 2
    run_id = args.run_id or f"perf-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    try:
        summary = measure_performance(
            run_id=run_id,
            machine=args.machine,
            agent_id=args.agent_id,
            batches=args.batches,
            batch_size=args.batch_size,
        )
    except PerformanceMeasureError as exc:
        print(f"Phase 3 performance measurement refused: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print("Phase 3 AWS-side performance measurement complete")
        print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
