"""EOD dataset API schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


DatasetStatus = Literal[
    "DISCOVERED",
    "MANIFESTED",
    "UPLOADING",
    "PARTIAL",
    "VALIDATING",
    "READY",
    "COMPLETE",
    "FAILED",
    "QUARANTINED",
    "CONFLICT",
]

FileStatus = Literal["MANIFESTED", "UPLOADING", "READY", "COMPLETE", "FAILED", "CONFLICT"]


class EodManifestFile(BaseModel):
    fileId: str | None = None
    relativePath: str
    datasetType: str
    sizeBytes: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)
    rowCount: int | None = Field(default=None, ge=0)

    @field_validator("sha256")
    @classmethod
    def lower_sha(cls, value: str) -> str:
        cleaned = value.lower()
        if any(ch not in "0123456789abcdef" for ch in cleaned):
            raise ValueError("sha256 must be hex")
        return cleaned


class EodManifestRegister(BaseModel):
    datasetId: str
    machine: str
    agentId: str
    sessionId: str | None = None
    tradingDate: str
    createdAt: str | None = None
    schemaVersion: str = "1"
    files: list[EodManifestFile] = Field(default_factory=list)


class EodQuarantineRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class EodDatasetFileView(BaseModel):
    fileId: str
    relativePath: str
    datasetType: str
    sizeBytes: int
    sha256: str
    rowCount: int | None = None
    storageKey: str | None = None
    bytesReceived: int
    status: FileStatus
    checksumStatus: str | None = None
    failureReason: str | None = None
    uploadedAt: str | None = None
    validatedAt: str | None = None


class EodDatasetView(BaseModel):
    datasetId: str
    machineId: str
    machine: str
    agentId: str
    sessionId: str | None = None
    tradingDate: str
    schemaVersion: str
    manifestCreatedAt: str | None = None
    status: DatasetStatus
    statusReason: str | None = None
    storageBackend: str
    totalFiles: int
    uploadedFiles: int
    totalBytes: int
    uploadedBytes: int
    completedAt: str | None = None
    finalizedAt: str | None = None
    rawDeletedAt: str | None = None
    receivedAt: str
    updatedAt: str
    files: list[EodDatasetFileView] = Field(default_factory=list)


class EodUploadAck(BaseModel):
    datasetId: str
    fileId: str
    status: FileStatus
    bytesReceived: int
    sizeBytes: int
    checksumStatus: str | None = None
    complete: bool


class EodActionResult(BaseModel):
    dataset: EodDatasetView


class EodReconciliationSummary(BaseModel):
    total: int
    byStatus: dict[str, int]
    missingFiles: int
    failedFiles: int
    checksumFailures: int
    partialDatasets: int
