"""Phase 3 EOD dataset landing coverage."""

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


def _configure_eod_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EOD_STORAGE_ROOT", str(tmp_path / "eod"))
    get_settings.cache_clear()


def _manifest(dataset_id: str, content: bytes, *, machine: str = SCOPED_MACHINE) -> dict:
    return {
        "datasetId": dataset_id,
        "machine": machine,
        "agentId": "agent-eod-test",
        "sessionId": "2026-08-10-NSE",
        "tradingDate": "2026-08-10",
        "createdAt": "2026-08-10T16:01:00+00:00",
        "schemaVersion": "1",
        "files": [
            {
                "fileId": "ticks",
                "relativePath": "ticks/NIFTY.jsonl",
                "datasetType": "ticks",
                "sizeBytes": len(content),
                "sha256": _sha(content),
                "rowCount": 2,
            }
        ],
    }


def test_eod_write_routes_are_fail_closed(
    client: TestClient, monkeypatch, tmp_path: Path
) -> None:
    _configure_eod_root(monkeypatch, tmp_path)
    dataset_id = _dataset_id("eod-auth")
    payload = _manifest(dataset_id, b"x\n")

    missing_manifest = client.post("/api/eod/manifests", json=payload)
    wrong_manifest = client.post(
        "/api/eod/manifests",
        json=payload,
        headers=agent_headers("wrong-token"),
    )
    missing_chunk = client.put(
        f"/api/eod/datasets/{dataset_id}/files/ticks/chunks?offset=0",
        content=b"x\n",
    )
    missing_complete = client.post(f"/api/eod/datasets/{dataset_id}/complete")
    missing_finalize = client.post(f"/api/eod/datasets/{dataset_id}/finalize")

    assert missing_manifest.status_code == 401
    assert wrong_manifest.status_code == 401
    assert missing_chunk.status_code == 401
    assert missing_complete.status_code == 401
    assert missing_finalize.status_code == 401


def test_eod_manifest_upload_complete_and_finalize(
    client: TestClient, monkeypatch, tmp_path: Path
) -> None:
    _configure_eod_root(monkeypatch, tmp_path)
    content = b'{"price": 101.25}\n{"price": 101.30}\n'
    dataset_id = _dataset_id("eod-ok")

    manifest = client.post(
        "/api/eod/manifests",
        json=_manifest(dataset_id, content),
        headers=agent_headers(SCOPED_TOKEN),
    )
    assert manifest.status_code == 200, manifest.text
    assert manifest.json()["status"] == "MANIFESTED"

    upload = client.put(
        f"/api/eod/datasets/{dataset_id}/files/ticks/chunks?offset=0",
        content=content,
        headers=agent_headers(SCOPED_TOKEN),
    )
    assert upload.status_code == 200, upload.text
    assert upload.json() == {
        "datasetId": dataset_id,
        "fileId": "ticks",
        "status": "READY",
        "bytesReceived": len(content),
        "sizeBytes": len(content),
        "checksumStatus": "PASSED",
        "complete": True,
    }
    validating = client.get(f"/api/eod/datasets/{dataset_id}")
    assert validating.status_code == 200, validating.text
    assert validating.json()["status"] == "VALIDATING"

    complete = client.post(
        f"/api/eod/datasets/{dataset_id}/complete",
        headers=agent_headers(SCOPED_TOKEN),
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["dataset"]["status"] == "READY"

    finalize = client.post(
        f"/api/eod/datasets/{dataset_id}/finalize",
        headers=agent_headers(SCOPED_TOKEN),
    )
    assert finalize.status_code == 200, finalize.text
    assert finalize.json()["dataset"]["status"] == "COMPLETE"

    detail = client.get(f"/api/eod/datasets/{dataset_id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["status"] == "COMPLETE"
    assert body["uploadedFiles"] == 1
    assert body["uploadedBytes"] == len(content)
    assert body["files"][0]["status"] == "COMPLETE"
    assert body["files"][0]["checksumStatus"] == "PASSED"

    reconciliation = client.get("/api/eod/reconciliation")
    assert reconciliation.status_code == 200, reconciliation.text
    assert reconciliation.json()["byStatus"]["COMPLETE"] >= 1


def test_eod_manifest_is_idempotent(client: TestClient, monkeypatch, tmp_path: Path) -> None:
    _configure_eod_root(monkeypatch, tmp_path)
    content = b"same manifest\n"
    dataset_id = _dataset_id("eod-idem")
    payload = _manifest(dataset_id, content)

    first = client.post("/api/eod/manifests", json=payload, headers=agent_headers(SCOPED_TOKEN))
    second = client.post("/api/eod/manifests", json=payload, headers=agent_headers(SCOPED_TOKEN))

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["datasetId"] == second.json()["datasetId"] == dataset_id
    assert len(second.json()["files"]) == 1
    assert second.json()["status"] == "MANIFESTED"


def test_eod_manifest_conflict_is_visible(client: TestClient, monkeypatch, tmp_path: Path) -> None:
    _configure_eod_root(monkeypatch, tmp_path)
    dataset_id = _dataset_id("eod-conflict")
    first = _manifest(dataset_id, b"original\n")
    changed = _manifest(dataset_id, b"changed\n")

    ok = client.post("/api/eod/manifests", json=first, headers=agent_headers(SCOPED_TOKEN))
    conflict = client.post("/api/eod/manifests", json=changed, headers=agent_headers(SCOPED_TOKEN))

    assert ok.status_code == 200, ok.text
    assert conflict.status_code == 200, conflict.text
    assert conflict.json()["status"] == "CONFLICT"
    assert "different manifest" in conflict.json()["statusReason"]


def test_eod_scoped_token_rejects_another_machine(
    client: TestClient, monkeypatch, tmp_path: Path
) -> None:
    _configure_eod_root(monkeypatch, tmp_path)
    response = client.post(
        "/api/eod/manifests",
        json=_manifest(_dataset_id("eod-scope"), b"x\n", machine="some-other-host"),
        headers=agent_headers(SCOPED_TOKEN),
    )
    assert response.status_code == 403


def test_eod_checksum_mismatch_fails_dataset(
    client: TestClient, monkeypatch, tmp_path: Path
) -> None:
    _configure_eod_root(monkeypatch, tmp_path)
    dataset_id = _dataset_id("eod-bad-sha")
    declared = _manifest(dataset_id, b"expected\n")
    actual = b"actual!!\n"

    manifest = client.post(
        "/api/eod/manifests",
        json=declared,
        headers=agent_headers(SCOPED_TOKEN),
    )
    assert manifest.status_code == 200, manifest.text

    upload = client.put(
        f"/api/eod/datasets/{dataset_id}/files/ticks/chunks?offset=0",
        content=actual,
        headers=agent_headers(SCOPED_TOKEN),
    )
    assert upload.status_code == 200, upload.text
    assert upload.json()["status"] == "FAILED"
    assert upload.json()["checksumStatus"] == "FAILED"

    detail = client.get(f"/api/eod/datasets/{dataset_id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["status"] == "FAILED"
    assert body["files"][0]["failureReason"] == "sha256 checksum mismatch"


def test_eod_checksum_failure_can_be_retried_and_finalized(
    client: TestClient, monkeypatch, tmp_path: Path
) -> None:
    _configure_eod_root(monkeypatch, tmp_path)
    expected = b'{"price": 101.25}\n{"price": 101.30}\n'
    corrupted = b'{"price": 101.25}\n{"price": 000.00}\n'
    dataset_id = _dataset_id("eod-retry-sha")

    manifest = client.post(
        "/api/eod/manifests",
        json=_manifest(dataset_id, expected),
        headers=agent_headers(SCOPED_TOKEN),
    )
    assert manifest.status_code == 200, manifest.text

    failed = client.put(
        f"/api/eod/datasets/{dataset_id}/files/ticks/chunks?offset=0",
        content=corrupted,
        headers=agent_headers(SCOPED_TOKEN),
    )
    assert failed.status_code == 200, failed.text
    assert failed.json()["status"] == "FAILED"
    assert failed.json()["checksumStatus"] == "FAILED"

    retried = client.put(
        f"/api/eod/datasets/{dataset_id}/files/ticks/chunks?offset=0",
        content=expected,
        headers=agent_headers(SCOPED_TOKEN),
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "READY"
    assert retried.json()["checksumStatus"] == "PASSED"

    complete = client.post(
        f"/api/eod/datasets/{dataset_id}/complete",
        headers=agent_headers(SCOPED_TOKEN),
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["dataset"]["status"] == "READY"

    finalize = client.post(
        f"/api/eod/datasets/{dataset_id}/finalize",
        headers=agent_headers(SCOPED_TOKEN),
    )
    assert finalize.status_code == 200, finalize.text
    assert finalize.json()["dataset"]["status"] == "COMPLETE"

    detail = client.get(f"/api/eod/datasets/{dataset_id}")
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["status"] == "COMPLETE"
    assert body["files"][0]["status"] == "COMPLETE"
    assert body["files"][0]["checksumStatus"] == "PASSED"

    events = client.get(f"/api/events?machineId={body['machineId']}&limit=20")
    assert events.status_code == 200, events.text
    event_types = {row["eventType"] for row in events.json()}
    assert "eod_checksum_failed" in event_types
    assert "eod_complete" in event_types


def test_eod_discovery_manifest_and_quarantine_states(
    client: TestClient, monkeypatch, tmp_path: Path
) -> None:
    _configure_eod_root(monkeypatch, tmp_path)
    content = b"discovered\n"
    dataset_id = _dataset_id("eod-discovered")
    payload = _manifest(dataset_id, content)

    discovered = client.post(
        "/api/eod/discoveries",
        json=payload,
        headers=agent_headers(SCOPED_TOKEN),
    )
    assert discovered.status_code == 200, discovered.text
    assert discovered.json()["status"] == "DISCOVERED"

    premature_upload = client.put(
        f"/api/eod/datasets/{dataset_id}/files/ticks/chunks?offset=0",
        content=content,
        headers=agent_headers(SCOPED_TOKEN),
    )
    assert premature_upload.status_code == 409

    manifested = client.post(
        "/api/eod/manifests",
        json=payload,
        headers=agent_headers(SCOPED_TOKEN),
    )
    assert manifested.status_code == 200, manifested.text
    assert manifested.json()["status"] == "MANIFESTED"

    quarantined = client.post(
        f"/api/eod/datasets/{dataset_id}/quarantine",
        json={"reason": "operator quarantined bad source bundle"},
        headers=agent_headers(SCOPED_TOKEN),
    )
    assert quarantined.status_code == 200, quarantined.text
    body = quarantined.json()["dataset"]
    assert body["status"] == "QUARANTINED"
    assert body["statusReason"] == "operator quarantined bad source bundle"

    blocked_finalize = client.post(
        f"/api/eod/datasets/{dataset_id}/finalize",
        headers=agent_headers(SCOPED_TOKEN),
    )
    assert blocked_finalize.status_code == 409
