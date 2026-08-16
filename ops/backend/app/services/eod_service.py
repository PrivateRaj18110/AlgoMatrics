"""End-of-day dataset landing service.

The EOD lane is observational data ingestion: Google/trading hosts push
manifests and bytes to AWS; AWS records catalog/progress/checksums and exposes
read-only reconciliation to the dashboard. It never sends control commands back
to a broker, strategy or VPS.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import re
from typing import Any
from uuid import uuid4

from app.core.config import get_settings
from app.repositories import eod_repo, events_repo, machines_repo
from app.schemas.eod import EodManifestFile, EodManifestRegister
from app.services.agent_service import LIVE_MACHINE_IDS, machine_id_for
from app.storage import DatasetStorage, get_dataset_storage

log = logging.getLogger("ops.eod")


class EodNotFoundError(LookupError):
    """Requested dataset or file does not exist."""


class EodConflictError(ValueError):
    """The caller attempted to mutate a conflicted or incompatible dataset."""


class EodValidationError(ValueError):
    """The caller sent a malformed EOD operation."""


_SAFE_FILE_ID = re.compile(r"^[a-zA-Z0-9_.=-]{1,160}$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _next_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def _parse_iso(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
    except ValueError:
        raise EodValidationError(f"invalid timestamp {value!r}") from None


def _derived_file_id(relative_path: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.=-]+", "_", relative_path.strip()).strip("._-")
    return slug[:160] or f"file-{uuid4().hex[:12]}"


def _normalise_file(file: EodManifestFile, storage: DatasetStorage, dataset_id: str) -> dict[str, Any]:
    file_id = (file.fileId or _derived_file_id(file.relativePath)).strip()
    if not _SAFE_FILE_ID.fullmatch(file_id):
        raise EodValidationError(
            "fileId must be 1-160 chars and contain only letters, digits, dot, underscore, equals or dash"
        )
    relative_path = file.relativePath.strip().replace("\\", "/")
    if not relative_path or relative_path.startswith("/") or ".." in relative_path.split("/"):
        raise EodValidationError("relativePath must be a safe relative path")
    dataset_type = file.datasetType.strip().lower()
    if not dataset_type:
        raise EodValidationError("datasetType is required")
    return {
        "fileId": file_id,
        "relativePath": relative_path,
        "datasetType": dataset_type,
        "sizeBytes": int(file.sizeBytes),
        "sha256": file.sha256.lower(),
        "rowCount": file.rowCount,
        "storageKey": storage.storage_key(dataset_id, file_id),
    }


def _manifest_signature(dataset: dict[str, Any], files: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "datasetId": dataset["datasetId"],
        "machineId": dataset["machineId"],
        "machine": dataset["machine"],
        "agentId": dataset["agentId"],
        "sessionId": dataset.get("sessionId"),
        "tradingDate": dataset["tradingDate"],
        "schemaVersion": str(dataset.get("schemaVersion", "1")),
        "files": sorted(
            (
                {
                    "fileId": file["fileId"],
                    "relativePath": file["relativePath"],
                    "datasetType": file["datasetType"],
                    "sizeBytes": int(file["sizeBytes"]),
                    "sha256": str(file["sha256"]).lower(),
                    "rowCount": file.get("rowCount"),
                }
                for file in files
            ),
            key=lambda row: row["fileId"],
        ),
    }


def _existing_signature(existing: dict[str, Any]) -> dict[str, Any]:
    return _manifest_signature(existing, existing.get("files", []))


def _emit_data_event(
    *,
    machine_id: str,
    machine: str,
    event_type: str,
    severity: str,
    message: str,
    dataset_id: str,
    session_id: str | None = None,
    payload_summary: str | None = None,
) -> None:
    event = {
        "id": _next_id("evt-eod"),
        "time": _now_iso(),
        "category": "data",
        "severity": severity,
        "source": machine,
        "message": message,
        "machine_id": machine_id,
        "machineId": machine_id,
        "event_type": event_type,
        "eventType": event_type,
        "session_id": session_id,
        "sessionId": session_id,
        "payload_summary": payload_summary or f"datasetId={dataset_id}",
        "payloadSummary": payload_summary or f"datasetId={dataset_id}",
    }
    events_repo.prepend(event)
    machines_repo.update(machine_id, {"lastEvent": event["time"]})


def _ensure_machine(machine_id: str, machine: str, agent_id: str, status: str) -> None:
    existing = machines_repo.get(machine_id)
    changes = {
        "agentId": agent_id,
        "lastEodStatus": status,
        "lastEvent": _now_iso(),
        "live": True,
    }
    if existing is not None:
        machines_repo.update(machine_id, changes)
        return
    machines_repo.upsert({
        "id": machine_id,
        "name": machine,
        "location": "EOD data source",
        "provider": "Raj Local Agent",
        "status": "online",
        "cpu": 0.0,
        "ram": 0.0,
        "disk": 0.0,
        "temperatureC": None,
        "internetMs": 0.0,
        "brokerPingMs": 0.0,
        "pythonStatus": "online",
        "uptimeSec": 0,
        "lastHeartbeat": "",
        "strategyCount": 0,
        "hostname": machine,
        **changes,
    })
    LIVE_MACHINE_IDS.add(machine_id)


def _validate_dataset_id(dataset_id: str) -> str:
    cleaned = dataset_id.strip()
    if not _SAFE_FILE_ID.fullmatch(cleaned):
        raise EodValidationError(
            "datasetId must be 1-160 chars and contain only letters, digits, dot, underscore, equals or dash"
        )
    return cleaned


def _validate_manifest(payload: EodManifestRegister) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    dataset_id = _validate_dataset_id(payload.datasetId)
    if not payload.files:
        raise EodValidationError("manifest must include at least one file")
    storage = get_dataset_storage()
    machine = payload.machine.strip()
    agent_id = payload.agentId.strip()
    if not machine:
        raise EodValidationError("machine is required")
    if not agent_id:
        raise EodValidationError("agentId is required")
    machine_id = machine_id_for(machine)
    dataset = {
        "datasetId": dataset_id,
        "machineId": machine_id,
        "machine": machine,
        "agentId": agent_id,
        "sessionId": payload.sessionId,
        "tradingDate": payload.tradingDate.strip(),
        "schemaVersion": str(payload.schemaVersion or "1"),
        "manifestCreatedAt": _parse_iso(payload.createdAt),
        "status": "MANIFESTED",
        "statusReason": None,
        "storageBackend": storage.backend_name,
    }
    if not dataset["tradingDate"]:
        raise EodValidationError("tradingDate is required")

    files = [_normalise_file(file, storage, dataset_id) for file in payload.files]
    file_ids = [file["fileId"] for file in files]
    paths = [file["relativePath"] for file in files]
    if len(set(file_ids)) != len(file_ids):
        raise EodValidationError("fileId values must be unique within a manifest")
    if len(set(paths)) != len(paths):
        raise EodValidationError("relativePath values must be unique within a manifest")
    return dataset, files


def register_manifest(payload: EodManifestRegister) -> dict[str, Any]:
    dataset, files = _validate_manifest(payload)
    _ensure_machine(dataset["machineId"], dataset["machine"], dataset["agentId"], "MANIFESTED")
    existing = eod_repo.get(dataset["datasetId"])
    if existing is not None:
        if _existing_signature(existing) == _manifest_signature(dataset, files):
            if existing["status"] == "DISCOVERED":
                manifested = eod_repo.update_dataset(
                    dataset["datasetId"],
                    {
                        "status": "MANIFESTED",
                        "statusReason": None,
                    },
                )
                _emit_data_event(
                    machine_id=dataset["machineId"],
                    machine=dataset["machine"],
                    event_type="eod_manifest",
                    severity="info",
                    message=f"EOD manifest received: {dataset['datasetId']}",
                    dataset_id=dataset["datasetId"],
                    session_id=dataset.get("sessionId"),
                    payload_summary=f"files={len(files)}, bytes={sum(file['sizeBytes'] for file in files)}",
                )
                return manifested or existing
            return existing
        reason = "dataset id already exists with different manifest metadata"
        conflicted = eod_repo.update_dataset(
            dataset["datasetId"],
            {"status": "CONFLICT", "statusReason": reason},
        )
        _emit_data_event(
            machine_id=dataset["machineId"],
            machine=dataset["machine"],
            event_type="eod_conflict",
            severity="critical",
            message=f"EOD dataset conflict: {dataset['datasetId']}",
            dataset_id=dataset["datasetId"],
            session_id=dataset.get("sessionId"),
            payload_summary=reason,
        )
        return conflicted or existing

    created = eod_repo.create(dataset, files)
    _emit_data_event(
        machine_id=dataset["machineId"],
        machine=dataset["machine"],
        event_type="eod_manifest",
        severity="info",
        message=f"EOD manifest received: {dataset['datasetId']}",
        dataset_id=dataset["datasetId"],
        session_id=dataset.get("sessionId"),
        payload_summary=f"files={len(files)}, bytes={sum(file['sizeBytes'] for file in files)}",
    )
    return created


def discover_dataset(payload: EodManifestRegister) -> dict[str, Any]:
    """Record a discovered EOD dataset before the final manifest is submitted."""
    dataset, files = _validate_manifest(payload)
    dataset["status"] = "DISCOVERED"
    dataset["statusReason"] = "dataset discovered; waiting for manifest registration"
    _ensure_machine(dataset["machineId"], dataset["machine"], dataset["agentId"], "DISCOVERED")
    existing = eod_repo.get(dataset["datasetId"])
    if existing is not None:
        if _existing_signature(existing) == _manifest_signature(dataset, files):
            return existing
        reason = "dataset id already exists with different discovery metadata"
        conflicted = eod_repo.update_dataset(
            dataset["datasetId"],
            {"status": "CONFLICT", "statusReason": reason},
        )
        _emit_data_event(
            machine_id=dataset["machineId"],
            machine=dataset["machine"],
            event_type="eod_conflict",
            severity="critical",
            message=f"EOD dataset discovery conflict: {dataset['datasetId']}",
            dataset_id=dataset["datasetId"],
            session_id=dataset.get("sessionId"),
            payload_summary=reason,
        )
        return conflicted or existing

    created = eod_repo.create(dataset, files)
    _emit_data_event(
        machine_id=dataset["machineId"],
        machine=dataset["machine"],
        event_type="eod_discovered",
        severity="info",
        message=f"EOD dataset discovered: {dataset['datasetId']}",
        dataset_id=dataset["datasetId"],
        session_id=dataset.get("sessionId"),
        payload_summary=f"files={len(files)}, bytes={sum(file['sizeBytes'] for file in files)}",
    )
    return created


def get_dataset(dataset_id: str) -> dict[str, Any]:
    dataset = eod_repo.get(dataset_id)
    if dataset is None:
        raise EodNotFoundError("dataset not found")
    return dataset


def list_datasets(
    *,
    limit: int = 100,
    status: str | None = None,
    machine_id: str | None = None,
    trading_date: str | None = None,
) -> list[dict[str, Any]]:
    return eod_repo.list(
        limit=limit,
        status=status,
        machine_id=machine_id,
        trading_date=trading_date,
    )


def reconciliation() -> dict[str, Any]:
    return eod_repo.reconciliation()


def _derive_dataset_status(dataset: dict[str, Any]) -> tuple[str, str | None]:
    files = dataset.get("files", [])
    if dataset.get("status") in {"DISCOVERED", "QUARANTINED", "CONFLICT"}:
        return dataset["status"], dataset.get("statusReason")
    if not files:
        return dataset.get("status") or "MANIFESTED", dataset.get("statusReason")
    if any(file["status"] in {"FAILED", "CONFLICT"} for file in files):
        return "FAILED", "one or more files failed validation"
    if all(file["status"] in {"READY", "COMPLETE"} for file in files):
        if dataset.get("completedAt") or dataset.get("finalizedAt"):
            return "READY", None
        return "VALIDATING", "all files uploaded; completion validation pending"
    if any(file["status"] == "READY" for file in files):
        return "PARTIAL", "some files are validated; waiting for remaining files"
    if any(file["status"] == "UPLOADING" for file in files):
        return "UPLOADING", "file upload in progress"
    if any(int(file.get("bytesReceived", 0)) > 0 for file in files):
        return "UPLOADING", "waiting for remaining files"
    return "MANIFESTED", None


def _update_rollup(dataset_id: str) -> dict[str, Any]:
    dataset = get_dataset(dataset_id)
    status, reason = _derive_dataset_status(dataset)
    return eod_repo.update_dataset(
        dataset_id,
        {"status": status, "statusReason": reason},
    ) or dataset


def upload_chunk(dataset_id: str, file_id: str, offset: int, data: bytes) -> dict[str, Any]:
    settings = get_settings()
    if len(data) > settings.eod_max_chunk_bytes:
        raise EodValidationError(f"chunk exceeds {settings.eod_max_chunk_bytes} bytes")
    if offset < 0:
        raise EodValidationError("offset must be non-negative")

    dataset = get_dataset(dataset_id)
    if dataset["status"] in {"DISCOVERED", "CONFLICT", "COMPLETE", "QUARANTINED"}:
        raise EodConflictError(f"dataset is {dataset['status']}")
    file = eod_repo.get_file(dataset_id, file_id)
    if file is None:
        raise EodNotFoundError("dataset file not found")
    size_bytes = int(file["sizeBytes"])
    if offset + len(data) > size_bytes:
        raise EodValidationError("chunk extends beyond declared file size")
    if offset > int(file.get("bytesReceived", 0)):
        raise EodValidationError("chunk offset leaves a gap in the uploaded file")

    storage = get_dataset_storage()
    try:
        bytes_received = storage.write_chunk(dataset_id, file_id, offset, data)
    except ValueError as exc:
        raise EodValidationError(str(exc)) from exc

    changes: dict[str, Any] = {
        "storageKey": storage.storage_key(dataset_id, file_id),
        "bytesReceived": bytes_received,
        "status": "UPLOADING" if bytes_received < size_bytes else "READY",
        "checksumStatus": None,
        "uploadedAt": _now_iso(),
    }
    if bytes_received == size_bytes:
        eod_repo.update_dataset(
            dataset_id,
            {"status": "VALIDATING", "statusReason": "validating uploaded file checksum"},
        )
        actual = storage.sha256(dataset_id, file_id)
        if actual.lower() == file["sha256"].lower():
            changes.update({
                "status": "READY",
                "checksumStatus": "PASSED",
                "validatedAt": _now_iso(),
                "failureReason": "",
            })
        else:
            reason = "sha256 checksum mismatch"
            changes.update({
                "status": "FAILED",
                "checksumStatus": "FAILED",
                "failureReason": reason,
                "validatedAt": _now_iso(),
            })
            eod_repo.update_dataset(dataset_id, {"status": "FAILED", "statusReason": reason})
            _emit_data_event(
                machine_id=dataset["machineId"],
                machine=dataset["machine"],
                event_type="eod_checksum_failed",
                severity="critical",
                message=f"EOD checksum failed: {dataset_id}/{file_id}",
                dataset_id=dataset_id,
                session_id=dataset.get("sessionId"),
                payload_summary=reason,
            )

    updated = eod_repo.update_file(dataset_id, file_id, changes)
    if updated is None:
        raise EodNotFoundError("dataset file not found")
    dataset = _update_rollup(dataset_id)
    machine_changes = {
        "lastEodStatus": dataset["status"],
    }
    if updated["status"] == "READY":
        machine_changes["lastSuccessfulUpload"] = _now_iso()
    machines_repo.update(dataset["machineId"], machine_changes)
    return {
        "datasetId": dataset_id,
        "fileId": file_id,
        "status": updated["status"],
        "bytesReceived": updated["bytesReceived"],
        "sizeBytes": updated["sizeBytes"],
        "checksumStatus": updated.get("checksumStatus"),
        "complete": updated["status"] in {"READY", "COMPLETE"},
    }


def complete_dataset(dataset_id: str) -> dict[str, Any]:
    dataset = get_dataset(dataset_id)
    if dataset["status"] in {"CONFLICT", "QUARANTINED"}:
        raise EodConflictError(f"dataset is {dataset['status']}")
    files = dataset.get("files", [])
    if any(file["status"] == "FAILED" for file in files):
        result = eod_repo.update_dataset(
            dataset_id,
            {"status": "FAILED", "statusReason": "one or more files failed validation"},
        )
    elif all(file["status"] in {"READY", "COMPLETE"} for file in files):
        result = eod_repo.update_dataset(
            dataset_id,
            {"status": "READY", "statusReason": None, "completedAt": _now_iso()},
        )
    else:
        result = eod_repo.update_dataset(
            dataset_id,
            {"status": "PARTIAL", "statusReason": "manifest completion requested before all files arrived"},
        )
    dataset = result or dataset
    machines_repo.update(dataset["machineId"], {"lastEodStatus": dataset["status"]})
    return dataset


def quarantine_dataset(dataset_id: str, reason: str) -> dict[str, Any]:
    dataset = get_dataset(dataset_id)
    cleaned = " ".join(reason.split())[:500]
    if not cleaned:
        raise EodValidationError("quarantine reason is required")
    result = eod_repo.update_dataset(
        dataset_id,
        {"status": "QUARANTINED", "statusReason": cleaned},
    )
    dataset = result or dataset
    machines_repo.update(dataset["machineId"], {"lastEodStatus": "QUARANTINED"})
    _emit_data_event(
        machine_id=dataset["machineId"],
        machine=dataset["machine"],
        event_type="eod_quarantined",
        severity="critical",
        message=f"EOD dataset quarantined: {dataset_id}",
        dataset_id=dataset_id,
        session_id=dataset.get("sessionId"),
        payload_summary=cleaned,
    )
    return dataset


def finalize_dataset(dataset_id: str) -> dict[str, Any]:
    dataset = get_dataset(dataset_id)
    if dataset["status"] in {"CONFLICT", "FAILED", "QUARANTINED"}:
        raise EodConflictError(f"dataset is {dataset['status']}")
    if not all(file["status"] in {"READY", "COMPLETE"} for file in dataset.get("files", [])):
        raise EodValidationError("all files must be checksum-validated before finalization")

    for file in dataset.get("files", []):
        eod_repo.update_file(dataset_id, file["fileId"], {"status": "COMPLETE"})
    result = eod_repo.update_dataset(
        dataset_id,
        {
            "status": "COMPLETE",
            "statusReason": None,
            "completedAt": dataset.get("completedAt") or _now_iso(),
            "finalizedAt": _now_iso(),
        },
    )
    dataset = result or get_dataset(dataset_id)
    machines_repo.update(dataset["machineId"], {
        "lastEodSync": dataset["finalizedAt"],
        "lastEodStatus": dataset["status"],
        "lastSuccessfulUpload": dataset["finalizedAt"],
    })
    _emit_data_event(
        machine_id=dataset["machineId"],
        machine=dataset["machine"],
        event_type="eod_complete",
        severity="info",
        message=f"EOD dataset finalized: {dataset_id}",
        dataset_id=dataset_id,
        session_id=dataset.get("sessionId"),
        payload_summary=f"files={dataset['uploadedFiles']}/{dataset['totalFiles']}",
    )
    try:
        from app.services.quant_service import analyze_dataset

        analyze_dataset(dataset_id)
    except Exception:
        log.exception("quant report generation failed dataset_id=%s", dataset_id)
    return dataset
