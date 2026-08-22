"""Phase 3 quant analytics and replay coverage."""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings
from fastapi.testclient import TestClient

from tests.conftest import SCOPED_MACHINE, SCOPED_TOKEN, agent_headers


def _dataset_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _configure_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EOD_STORAGE_ROOT", str(tmp_path / "eod"))
    get_settings.cache_clear()


def _manifest(dataset_id: str, trades: bytes, candles: bytes) -> dict:
    return {
        "datasetId": dataset_id,
        "machine": SCOPED_MACHINE,
        "agentId": "agent-quant-test",
        "sessionId": "2026-08-10-NSE",
        "tradingDate": "2026-08-10",
        "createdAt": "2026-08-10T16:05:00+00:00",
        "schemaVersion": "1",
        "files": [
            {
                "fileId": "trades",
                "relativePath": "trades/executions.jsonl",
                "datasetType": "trades",
                "sizeBytes": len(trades),
                "sha256": _sha(trades),
                "rowCount": 3,
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


def _upload_and_finalize(
    client: TestClient,
    dataset_id: str,
    trades: bytes,
    candles: bytes,
) -> None:
    manifest = client.post(
        "/api/eod/manifests",
        json=_manifest(dataset_id, trades, candles),
        headers=agent_headers(SCOPED_TOKEN),
    )
    assert manifest.status_code == 200, manifest.text
    for file_id, payload in (("trades", trades), ("candles", candles)):
        upload = client.put(
            f"/api/eod/datasets/{dataset_id}/files/{file_id}/chunks?offset=0",
            content=payload,
            headers=agent_headers(SCOPED_TOKEN),
        )
        assert upload.status_code == 200, upload.text
        assert upload.json()["checksumStatus"] == "PASSED"
    complete = client.post(
        f"/api/eod/datasets/{dataset_id}/complete",
        headers=agent_headers(SCOPED_TOKEN),
    )
    assert complete.status_code == 200, complete.text
    finalize = client.post(
        f"/api/eod/datasets/{dataset_id}/finalize",
        headers=agent_headers(SCOPED_TOKEN),
    )
    assert finalize.status_code == 200, finalize.text


def test_finalized_eod_dataset_generates_quant_report(
    client: TestClient, monkeypatch, tmp_path: Path
) -> None:
    _configure_root(monkeypatch, tmp_path)
    dataset_id = _dataset_id("quant-eod")
    trades = (
        b'{"time":"2026-08-10T09:20:00+05:30","symbol":"NIFTY","strategy":"alpha","pnl":100}\n'
        b'{"time":"2026-08-10T10:10:00+05:30","symbol":"NIFTY","strategy":"alpha","pnl":-40}\n'
        b'{"time":"2026-08-10T11:45:00+05:30","symbol":"BANKNIFTY","strategy":"beta","pnl":70}\n'
    )
    candles = (
        b"time,symbol,close\n"
        b"2026-08-10T09:15:00+05:30,NIFTY,100\n"
        b"2026-08-10T09:16:00+05:30,NIFTY,105\n"
        b"2026-08-10T09:17:00+05:30,NIFTY,102\n"
        b"2026-08-10T09:18:00+05:30,NIFTY,110\n"
    )

    _upload_and_finalize(client, dataset_id, trades, candles)

    report = client.get(f"/api/quant/datasets/{dataset_id}/report")
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["datasetId"] == dataset_id
    assert body["status"] == "READY"
    assert body["coverage"]["sessionId"] == "2026-08-10-NSE"
    assert body["coverage"]["parsedFiles"] == 2
    assert body["coverage"]["parsedRows"] == 7
    assert body["tradeMetrics"]["totalTrades"] == 3
    assert body["tradeMetrics"]["closedTrades"] == 3
    assert body["tradeMetrics"]["grossPnl"] == 130
    assert body["tradeMetrics"]["winningTrades"] == 2
    assert body["tradeMetrics"]["losingTrades"] == 1
    assert body["tradeMetrics"]["profitFactor"] == 4.25
    assert body["marketReplay"]["available"] is True
    assert body["marketReplay"]["returnPct"] == 10
    assert len(body["marketReplay"]["points"]) == 4
    assert body["analytics"]["performance"]["status"] == "AVAILABLE"
    assert body["analytics"]["performance"]["metrics"]["grossPnl"]["value"] == 130
    assert body["analytics"]["execution"]["status"] == "AVAILABLE"
    assert body["analytics"]["execution"]["metrics"]["totalFees"]["status"] == "NOT_AVAILABLE"
    assert body["analytics"]["signals"]["status"] == "NOT_AVAILABLE"
    assert body["analytics"]["sessions"]["status"] == "AVAILABLE"
    assert body["analytics"]["dataQuality"]["status"] == "AVAILABLE"

    reports = client.get("/api/quant/reports")
    assert reports.status_code == 200, reports.text
    assert any(row["datasetId"] == dataset_id for row in reports.json())


def test_quant_analytics_category_endpoint(client: TestClient, monkeypatch, tmp_path: Path) -> None:
    _configure_root(monkeypatch, tmp_path)
    dataset_id = _dataset_id("quant-analytics")
    trades = (
        b'{"time":"2026-08-10T09:20:00+05:30","symbol":"NIFTY","strategy":"alpha","pnl":25}\n'
        b'{"time":"2026-08-10T10:10:00+05:30","symbol":"NIFTY","strategy":"alpha","pnl":-5}\n'
    )
    candles = (
        b"time,symbol,close\n"
        b"2026-08-10T09:15:00+05:30,NIFTY,100\n"
        b"2026-08-10T09:16:00+05:30,NIFTY,101\n"
    )

    _upload_and_finalize(client, dataset_id, trades, candles)

    performance = client.get(f"/api/quant/analytics/performance?datasetId={dataset_id}")
    assert performance.status_code == 200, performance.text
    performance_body = performance.json()
    assert performance_body["category"] == "performance"
    assert performance_body["calculationVersion"] == "phase3-quant-analytics-v1"
    assert performance_body["reportCount"] == 1
    assert performance_body["reports"][0]["datasetId"] == dataset_id
    assert performance_body["reports"][0]["analytics"]["status"] == "AVAILABLE"
    assert performance_body["reports"][0]["analytics"]["metrics"]["closedTrades"]["value"] == 2

    signals = client.get(f"/api/quant/analytics/signals?datasetId={dataset_id}")
    assert signals.status_code == 200, signals.text
    assert signals.json()["reports"][0]["analytics"]["status"] == "NOT_AVAILABLE"


def test_quant_report_requires_finalized_dataset(client: TestClient) -> None:
    missing = client.get(f"/api/quant/datasets/{_dataset_id('missing')}/report")
    assert missing.status_code == 404


def test_synthetic_replay_is_deterministic_and_bounded(client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("QUANT_SYNTHETIC_MAX_STEPS", "50")
    get_settings.cache_clear()
    payload = {
        "seed": 7,
        "symbol": "SYNTH-NIFTY",
        "steps": 250,
        "startPrice": 100.0,
        "driftBps": 1.0,
        "volatilityBps": 10.0,
    }

    first = client.post("/api/quant/replays/synthetic", json=payload)
    second = client.post("/api/quant/replays/synthetic", json=payload)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json() == second.json()
    assert first.json()["steps"] == 50
    assert first.json()["replay"]["available"] is True
    assert first.json()["tradeMetrics"]["totalTrades"] == 1
