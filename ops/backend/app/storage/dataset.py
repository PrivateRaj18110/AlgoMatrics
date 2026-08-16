"""Storage port for EOD dataset bytes.

The ops API is the AWS-side landing authority for data, not a trading runtime.
This module deliberately exposes only file-write/read/checksum primitives for
dataset ingestion and validation.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from abc import ABC, abstractmethod
from io import BytesIO
from pathlib import Path
from typing import Any

from app.core.config import get_settings

_SAFE = re.compile(r"[^a-zA-Z0-9_.=-]+")


def _safe_part(value: str) -> str:
    cleaned = _SAFE.sub("_", value.strip())
    return cleaned[:160] or "unknown"


class DatasetStorage(ABC):
    """Abstract storage backend for raw EOD files."""

    backend_name = "abstract"

    @abstractmethod
    def storage_key(self, dataset_id: str, file_id: str) -> str:
        """Opaque storage key for one uploaded file."""

    @abstractmethod
    def write_chunk(self, dataset_id: str, file_id: str, offset: int, data: bytes) -> int:
        """Write a chunk at ``offset``. Returns the resulting object size."""

    @abstractmethod
    def size(self, dataset_id: str, file_id: str) -> int:
        """Current byte size of the staged object."""

    @abstractmethod
    def sha256(self, dataset_id: str, file_id: str) -> str:
        """SHA256 of the staged object."""

    @abstractmethod
    def read_bytes(self, dataset_id: str, file_id: str, *, max_bytes: int) -> bytes:
        """Read at most ``max_bytes`` from a staged object."""

    @abstractmethod
    def exists(self, dataset_id: str, file_id: str) -> bool:
        """Whether the staged object exists."""

    @abstractmethod
    def delete_dataset(self, dataset_id: str) -> int:
        """Delete all raw objects for a dataset. Returns objects/files removed."""


class LocalDatasetStorage(DatasetStorage):
    """Filesystem-backed storage for local/dev/test deployments."""

    backend_name = "local"

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    def _path(self, dataset_id: str, file_id: str) -> Path:
        return self._root / _safe_part(dataset_id) / f"{_safe_part(file_id)}.part"

    def storage_key(self, dataset_id: str, file_id: str) -> str:
        path = self._path(dataset_id, file_id)
        return str(path.relative_to(self._root)).replace("\\", "/")

    def write_chunk(self, dataset_id: str, file_id: str, offset: int, data: bytes) -> int:
        if offset < 0:
            raise ValueError("offset must be non-negative")
        path = self._path(dataset_id, file_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "r+b" if path.exists() else "w+b"
        with path.open(mode) as fh:
            current = path.stat().st_size if path.exists() else 0
            if offset > current:
                raise ValueError(f"offset {offset} is beyond current size {current}")
            fh.seek(offset)
            fh.write(data)
            fh.truncate(max(current, offset + len(data)))
        return path.stat().st_size

    def size(self, dataset_id: str, file_id: str) -> int:
        path = self._path(dataset_id, file_id)
        return path.stat().st_size if path.exists() else 0

    def sha256(self, dataset_id: str, file_id: str) -> str:
        path = self._path(dataset_id, file_id)
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def read_bytes(self, dataset_id: str, file_id: str, *, max_bytes: int) -> bytes:
        if max_bytes < 0:
            raise ValueError("max_bytes must be non-negative")
        path = self._path(dataset_id, file_id)
        with path.open("rb") as fh:
            return fh.read(max_bytes)

    def exists(self, dataset_id: str, file_id: str) -> bool:
        return self._path(dataset_id, file_id).is_file()

    def delete_dataset(self, dataset_id: str) -> int:
        root = self._root / _safe_part(dataset_id)
        if not root.exists():
            return 0
        count = sum(1 for path in root.rglob("*") if path.is_file())
        shutil.rmtree(root)
        return count


def _safe_prefix(value: str) -> str:
    cleaned = value.strip().replace("\\", "/").strip("/")
    if not cleaned:
        return ""
    parts = [part for part in cleaned.split("/") if part and part != "."]
    if any(part == ".." for part in parts):
        raise ValueError("object storage prefix must not contain '..'")
    return "/".join(_safe_part(part) for part in parts)


def _read_body(response: dict[str, Any]) -> bytes:
    body = response["Body"]
    if isinstance(body, bytes):
        return body
    if isinstance(body, BytesIO):
        return body.read()
    return body.read()


def _is_missing_key(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return False
    code = str(response.get("Error", {}).get("Code", ""))
    return code in {"NoSuchKey", "NoSuchBucket", "404", "NotFound"}


class ObjectDatasetStorage(DatasetStorage):
    """S3-compatible object storage using chunk objects plus a small index.

    Object stores do not offer safe random append/truncate semantics. This
    adapter therefore stages every API chunk as its own object and stores a
    bounded JSON index beside it. Retries are idempotent when the same offset
    carries the same bytes; conflicting rewrites fail visibly instead of
    silently corrupting the dataset.
    """

    backend_name = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "algomatrics/eod",
        region_name: str | None = None,
        endpoint_url: str | None = None,
        force_path_style: bool = False,
        server_side_encryption: str | None = None,
        client: Any | None = None,
    ) -> None:
        bucket = bucket.strip()
        if not bucket:
            raise ValueError("EOD_S3_BUCKET is required for object storage")
        self._bucket = bucket
        self._prefix = _safe_prefix(prefix)
        self._server_side_encryption = (server_side_encryption or "").strip() or None
        self._client = client or self._build_client(
            region_name=region_name,
            endpoint_url=endpoint_url,
            force_path_style=force_path_style,
        )

    @staticmethod
    def _build_client(
        *,
        region_name: str | None,
        endpoint_url: str | None,
        force_path_style: bool,
    ) -> Any:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - depends on deployment image
            raise RuntimeError(
                "EOD object storage requires boto3. Install ops/backend requirements "
                "or use EOD_STORAGE_BACKEND=local for development."
            ) from exc

        config = Config(s3={"addressing_style": "path"}) if force_path_style else None
        kwargs: dict[str, Any] = {}
        if region_name:
            kwargs["region_name"] = region_name
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        if config is not None:
            kwargs["config"] = config
        return boto3.client("s3", **kwargs)

    def _base_key(self, dataset_id: str, file_id: str) -> str:
        parts = [
            self._prefix,
            "datasets",
            _safe_part(dataset_id),
            _safe_part(file_id),
        ]
        return "/".join(part for part in parts if part)

    def _index_key(self, dataset_id: str, file_id: str) -> str:
        return f"{self._base_key(dataset_id, file_id)}/index.json"

    def _chunk_key(self, dataset_id: str, file_id: str, offset: int) -> str:
        return f"{self._base_key(dataset_id, file_id)}/chunks/{offset:020d}"

    def _put_bytes(self, key: str, body: bytes, *, metadata: dict[str, str] | None = None) -> None:
        kwargs: dict[str, Any] = {
            "Bucket": self._bucket,
            "Key": key,
            "Body": body,
        }
        if metadata:
            kwargs["Metadata"] = metadata
        if self._server_side_encryption:
            kwargs["ServerSideEncryption"] = self._server_side_encryption
        self._client.put_object(**kwargs)

    def _get_bytes(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return _read_body(response)

    def _empty_index(self, dataset_id: str, file_id: str) -> dict[str, Any]:
        return {
            "schemaVersion": 1,
            "datasetId": dataset_id,
            "fileId": file_id,
            "chunks": [],
        }

    def _load_index(self, dataset_id: str, file_id: str) -> dict[str, Any]:
        try:
            raw = self._get_bytes(self._index_key(dataset_id, file_id))
        except Exception as exc:
            if _is_missing_key(exc):
                return self._empty_index(dataset_id, file_id)
            raise
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("chunks"), list):
            raise ValueError("object storage index is corrupt")
        return payload

    def _save_index(self, dataset_id: str, file_id: str, index: dict[str, Any]) -> None:
        body = json.dumps(index, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self._put_bytes(
            self._index_key(dataset_id, file_id),
            body,
            metadata={"content-sha256": hashlib.sha256(body).hexdigest()},
        )

    @staticmethod
    def _chunks(index: dict[str, Any]) -> list[dict[str, Any]]:
        chunks = []
        for chunk in index.get("chunks", []):
            chunks.append({
                "offset": int(chunk["offset"]),
                "length": int(chunk["length"]),
                "sha256": str(chunk["sha256"]),
                "key": str(chunk["key"]),
            })
        return sorted(chunks, key=lambda row: row["offset"])

    def _contiguous_size(self, index: dict[str, Any]) -> int:
        expected = 0
        for chunk in self._chunks(index):
            if chunk["offset"] != expected:
                break
            expected += chunk["length"]
        return expected

    def storage_key(self, dataset_id: str, file_id: str) -> str:
        return f"s3://{self._bucket}/{self._base_key(dataset_id, file_id)}/"

    def write_chunk(self, dataset_id: str, file_id: str, offset: int, data: bytes) -> int:
        if offset < 0:
            raise ValueError("offset must be non-negative")
        index = self._load_index(dataset_id, file_id)
        current = self._contiguous_size(index)
        digest = hashlib.sha256(data).hexdigest()

        for chunk in self._chunks(index):
            if chunk["offset"] != offset:
                continue
            if chunk["length"] == len(data) and chunk["sha256"] == digest:
                return current
            raise ValueError("offset has already been written with different bytes")

        if offset > current:
            raise ValueError(f"offset {offset} is beyond current size {current}")
        if offset < current:
            raise ValueError("offset is inside an already written range")

        key = self._chunk_key(dataset_id, file_id, offset)
        self._put_bytes(
            key,
            data,
            metadata={"chunk-sha256": digest, "offset": str(offset), "length": str(len(data))},
        )
        index["chunks"] = [
            *self._chunks(index),
            {"offset": offset, "length": len(data), "sha256": digest, "key": key},
        ]
        self._save_index(dataset_id, file_id, index)
        return self._contiguous_size(index)

    def size(self, dataset_id: str, file_id: str) -> int:
        return self._contiguous_size(self._load_index(dataset_id, file_id))

    def sha256(self, dataset_id: str, file_id: str) -> str:
        digest = hashlib.sha256()
        expected = 0
        for chunk in self._chunks(self._load_index(dataset_id, file_id)):
            if chunk["offset"] != expected:
                raise ValueError("object storage chunks are not contiguous")
            data = self._get_bytes(chunk["key"])
            if hashlib.sha256(data).hexdigest() != chunk["sha256"]:
                raise ValueError("object storage chunk checksum mismatch")
            digest.update(data)
            expected += chunk["length"]
        return digest.hexdigest()

    def read_bytes(self, dataset_id: str, file_id: str, *, max_bytes: int) -> bytes:
        if max_bytes < 0:
            raise ValueError("max_bytes must be non-negative")
        remaining = max_bytes
        out = bytearray()
        expected = 0
        for chunk in self._chunks(self._load_index(dataset_id, file_id)):
            if remaining <= 0:
                break
            if chunk["offset"] != expected:
                break
            data = self._get_bytes(chunk["key"])
            if hashlib.sha256(data).hexdigest() != chunk["sha256"]:
                raise ValueError("object storage chunk checksum mismatch")
            out.extend(data[:remaining])
            remaining -= min(remaining, len(data))
            expected += chunk["length"]
        return bytes(out)

    def exists(self, dataset_id: str, file_id: str) -> bool:
        return self.size(dataset_id, file_id) > 0

    def delete_dataset(self, dataset_id: str) -> int:
        base = "/".join(part for part in [self._prefix, "datasets", _safe_part(dataset_id)] if part)
        prefix = f"{base}/"
        try:
            paginator = self._client.get_paginator("list_objects_v2")
        except AttributeError:  # pragma: no cover - boto3 clients provide this
            return 0

        removed = 0
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
            for batch_start in range(0, len(objects), 1000):
                batch = objects[batch_start: batch_start + 1000]
                if not batch:
                    continue
                self._client.delete_objects(Bucket=self._bucket, Delete={"Objects": batch})
                removed += len(batch)
        return removed


S3DatasetStorage = ObjectDatasetStorage


def get_dataset_storage() -> DatasetStorage:
    settings = get_settings()
    backend = settings.eod_storage_backend.strip().lower()
    if backend in {"", "local", "filesystem"}:
        return LocalDatasetStorage(settings.eod_storage_root)
    if backend in {"s3", "object", "object-storage", "s3-compatible"}:
        return ObjectDatasetStorage(
            bucket=settings.eod_s3_bucket or "",
            prefix=settings.eod_s3_prefix,
            region_name=settings.eod_s3_region,
            endpoint_url=settings.eod_s3_endpoint_url,
            force_path_style=settings.eod_s3_force_path_style,
            server_side_encryption=settings.eod_s3_server_side_encryption,
        )
    raise RuntimeError(
        f"EOD storage backend {settings.eod_storage_backend!r} is not available in this build"
    )
