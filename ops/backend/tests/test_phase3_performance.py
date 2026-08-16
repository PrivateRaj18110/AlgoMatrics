"""Phase 3 local performance-measurement harness coverage."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]

AGENT_TOKEN = "phase3-performance-agent-token"  # noqa: S105
DASHBOARD_TOKEN = "phase3-performance-dashboard-token"  # noqa: S105


def _environment(database_url: str | None, storage_root: Path | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (str(BACKEND_DIR), env.get("PYTHONPATH", "")) if part
    )
    env["RAJ_AGENT_TOKEN"] = AGENT_TOKEN
    env["RAJ_DASHBOARD_TOKEN"] = DASHBOARD_TOKEN
    env["OPS_REST_AUTH_REQUIRED"] = "true"
    env.pop("RAJ_AGENT_TOKENS", None)
    env.pop("ENVIRONMENT", None)
    if database_url is None:
        env.pop("DATABASE_URL", None)
    else:
        env["DATABASE_URL"] = database_url
    if storage_root is not None:
        env["EOD_STORAGE_ROOT"] = str(storage_root)
    return env


def _migrate(database_url: str, storage_root: Path) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=_environment(database_url, storage_root),
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _run_measurement(
    database_url: str | None,
    storage_root: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.measure_phase3_performance",
            "--json",
            "--run-id",
            "pytest-phase3-perf",
            "--batches",
            "1",
            "--batch-size",
            "4",
        ],
        cwd=BACKEND_DIR,
        env=_environment(database_url, storage_root),
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )


def test_phase3_performance_measurement_outputs_acceptance_metrics(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'phase3-perf.db').as_posix()}"
    storage_root = tmp_path / "eod"
    _migrate(database_url, storage_root)

    result = _run_measurement(database_url, storage_root)
    assert result.returncode == 0, result.stderr + result.stdout

    body = json.loads(result.stdout.strip().splitlines()[-1])
    measurements = body["measurements"]
    ingest = measurements["ingestion"]
    websocket = measurements["websocketBroadcast"]
    dashboard = measurements["dashboardReads"]
    eod_quant = measurements["eodAndQuant"]

    assert body["environment"]["production"] is False
    assert body["environment"]["database"] == "configured"
    assert ingest["submitted"] == 4
    assert ingest["accepted"] == 4
    assert ingest["throughputEnvelopesPerSec"] > 0
    assert ingest["requestLatencyMs"]["p50"] > 0
    assert ingest["writeLatencyMsPerEnvelope"] > 0
    assert ingest["duplicateReplay"]["duplicates"] == 4
    assert ingest["duplicateReplay"]["latencyMs"] > 0

    assert websocket["authenticated"] is True
    assert websocket["initialType"] == "machines"
    assert websocket["notificationType"] == "event"
    assert websocket["latencyMs"] > 0

    assert dashboard["machines"]["latencyMs"] > 0
    assert dashboard["events"]["latencyMs"] > 0
    assert dashboard["events"]["rows"] >= 5
    assert dashboard["recovery"]["latencyMs"] > 0

    assert eod_quant["manifestLatencyMs"] > 0
    assert eod_quant["uploadLatencyMs"] > 0
    assert eod_quant["completeLatencyMs"] > 0
    assert eod_quant["finalizeAndAnalyzeLatencyMs"] > 0
    assert eod_quant["quantReportReadLatencyMs"] > 0
    assert eod_quant["completeStatus"] == "READY"
    assert eod_quant["finalStatus"] == "COMPLETE"
    assert eod_quant["quantStatus"] == "READY"
    assert eod_quant["quantClosedTrades"] == 2
    assert eod_quant["quantReplayAvailable"] is True


def test_phase3_performance_measurement_refuses_without_database(tmp_path: Path) -> None:
    result = _run_measurement(None, tmp_path / "eod")

    assert result.returncode == 1
    assert "DATABASE_URL is required" in result.stderr
