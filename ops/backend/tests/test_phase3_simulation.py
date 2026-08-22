"""Deterministic AWS-side Phase 3 local simulation coverage."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]

AGENT_TOKEN = "phase3-simulation-agent-token"  # noqa: S105
DASHBOARD_TOKEN = "phase3-simulation-dashboard-token"  # noqa: S105


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


def _run_simulation(
    database_url: str | None,
    storage_root: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.run_phase3_simulation",
            "--json",
            "--seed",
            "1337",
            "--run-id",
            "pytest-phase3-sim",
        ],
        cwd=BACKEND_DIR,
        env=_environment(database_url, storage_root),
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )


def test_phase3_simulation_exercises_full_aws_side_flow(tmp_path: Path) -> None:
    database_url = f"sqlite:///{(tmp_path / 'phase3-sim.db').as_posix()}"
    storage_root = tmp_path / "eod"
    _migrate(database_url, storage_root)

    result = _run_simulation(database_url, storage_root)
    assert result.returncode == 0, result.stderr + result.stdout

    summary = json.loads(result.stdout.strip().splitlines()[-1])
    assert summary["authorityBoundary"] == {
        "awsToGoogleControlPath": False,
        "brokerCallsExercised": False,
        "tradingControlsExercised": False,
    }

    assert summary["acks"]["initialOffline"]["processed"] == 9
    assert summary["acks"]["initialOffline"]["rejected"] == 1
    assert summary["failureInjection"]["deadLetters"] == 1
    assert summary["failureInjection"]["duplicateReplaySafe"] is True
    assert summary["failureInjection"]["sequenceGapVisible"] is True
    assert summary["acks"]["duplicateReplay"]["duplicate"] == 2

    assert summary["recovery"]["offlineStatus"] == "offline"
    assert summary["recovery"]["offlineState"] == "offline"
    assert summary["recovery"]["offlineDurationSec"] > 0
    assert summary["recovery"]["onlineStatus"] == "online"
    assert summary["recovery"]["onlineState"] == "online"
    assert summary["recovery"]["missingEvents"] == 2
    assert summary["recovery"]["gapCount"] == 1

    assert summary["websocket"]["authenticated"] is True
    assert summary["websocket"]["observedMessages"] >= 6
    assert "machines" in summary["websocket"]["messageTypes"]
    assert "event" in summary["websocket"]["messageTypes"]

    assert summary["dashboard"]["machineStatus"] == "online"
    assert summary["dashboard"]["timelineEvents"] >= 10
    assert summary["dashboard"]["riskEvents"] == 1
    assert summary["dashboard"]["boundedPayloadPreview"] is True

    assert summary["eod"]["manifestStatus"] == "MANIFESTED"
    assert summary["eod"]["uploadStatuses"] == ["UPLOADING", "READY", "READY"]
    assert summary["eod"]["checksumPassed"] is True
    assert summary["eod"]["completeStatus"] == "READY"
    assert summary["eod"]["finalStatus"] == "COMPLETE"
    assert summary["eod"]["reconciliation"]["byStatus"]["COMPLETE"] == 1
    assert summary["eod"]["reconciliation"]["checksumFailures"] == 0

    assert summary["quant"]["status"] == "READY"
    assert summary["quant"]["closedTrades"] == 2
    assert summary["quant"]["grossPnl"] == 1.0
    assert summary["quant"]["replayAvailable"] is True
    assert summary["quant"]["points"] == 4


def test_phase3_simulation_refuses_without_database(tmp_path: Path) -> None:
    result = _run_simulation(None, tmp_path / "eod")

    assert result.returncode == 1
    assert "DATABASE_URL is required" in result.stderr
