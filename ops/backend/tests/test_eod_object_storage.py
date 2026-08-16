"""Phase 3 EOD object-storage adapter coverage."""

from __future__ import annotations

import hashlib
import json
from io import BytesIO
from typing import Any

import pytest
from app.core.config import Settings, get_settings
from app.storage.dataset import ObjectDatasetStorage, get_dataset_storage


class _MissingObject(Exception):
    def __init__(self) -> None:
        super().__init__("object not found")
        self.response = {"Error": {"Code": "NoSuchKey"}}


class _FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.puts: list[dict[str, Any]] = []

    def put_object(self, **kwargs: Any) -> None:
        key = (kwargs["Bucket"], kwargs["Key"])
        body = kwargs["Body"]
        self.objects[key] = body if isinstance(body, bytes) else bytes(body)
        self.puts.append(kwargs)

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        try:
            body = self.objects[(Bucket, Key)]
        except KeyError as exc:
            raise _MissingObject from exc
        return {"Body": BytesIO(body)}

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        try:
            body = self.objects[(Bucket, Key)]
        except KeyError as exc:
            raise _MissingObject from exc
        return {"ContentLength": len(body)}


def _storage(fake: _FakeS3 | None = None) -> ObjectDatasetStorage:
    return ObjectDatasetStorage(
        bucket="algo-eod",
        prefix="phase3/eod",
        server_side_encryption="AES256",
        client=fake or _FakeS3(),
    )


def test_object_storage_chunks_are_resumable_and_checksum_safe() -> None:
    fake = _FakeS3()
    storage = _storage(fake)

    assert (
        storage.storage_key("dataset-1", "ticks")
        == "s3://algo-eod/phase3/eod/datasets/dataset-1/ticks/"
    )
    assert storage.exists("dataset-1", "ticks") is False
    assert storage.write_chunk("dataset-1", "ticks", 0, b"abc") == 3
    assert storage.write_chunk("dataset-1", "ticks", 3, b"def") == 6
    assert storage.exists("dataset-1", "ticks") is True
    assert storage.size("dataset-1", "ticks") == 6
    assert storage.read_bytes("dataset-1", "ticks", max_bytes=4) == b"abcd"
    assert storage.sha256("dataset-1", "ticks") == hashlib.sha256(b"abcdef").hexdigest()
    assert all(put.get("ServerSideEncryption") == "AES256" for put in fake.puts)


def test_object_storage_retries_are_idempotent_but_conflicts_fail() -> None:
    storage = _storage()

    assert storage.write_chunk("dataset-2", "ticks", 0, b"abc") == 3
    assert storage.write_chunk("dataset-2", "ticks", 0, b"abc") == 3

    with pytest.raises(ValueError, match="different bytes"):
        storage.write_chunk("dataset-2", "ticks", 0, b"xyz")

    with pytest.raises(ValueError, match="beyond current size"):
        storage.write_chunk("dataset-2", "ticks", 10, b"gap")


def test_object_storage_detects_corrupt_index() -> None:
    fake = _FakeS3()
    storage = _storage(fake)
    fake.objects[("algo-eod", "phase3/eod/datasets/dataset-3/ticks/index.json")] = json.dumps(
        {"schemaVersion": 1, "chunks": "not-a-list"}
    ).encode()

    with pytest.raises(ValueError, match="index is corrupt"):
        storage.size("dataset-3", "ticks")


def test_object_storage_read_detects_corrupt_chunk() -> None:
    fake = _FakeS3()
    storage = _storage(fake)

    storage.write_chunk("dataset-4", "ticks", 0, b"abc")
    chunk_key = "phase3/eod/datasets/dataset-4/ticks/chunks/00000000000000000000"
    fake.objects[("algo-eod", chunk_key)] = b"xyz"

    with pytest.raises(ValueError, match="chunk checksum mismatch"):
        storage.read_bytes("dataset-4", "ticks", max_bytes=1)


def test_object_storage_factory_requires_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EOD_STORAGE_BACKEND", "s3")
    monkeypatch.delenv("EOD_S3_BUCKET", raising=False)
    get_settings.cache_clear()
    try:
        with pytest.raises(ValueError, match="EOD_S3_BUCKET"):
            get_dataset_storage()
    finally:
        get_settings.cache_clear()


def test_production_s3_configuration_requires_bucket() -> None:
    with pytest.raises(RuntimeError) as excinfo:
        Settings(
            environment="production",
            database_url="sqlite:///ops.db",
            raj_agent_token="agent-token",  # noqa: S106 - test credential
            raj_dashboard_token="dashboard-token",  # noqa: S106 - test credential
            eod_storage_backend="s3",
        ).assert_production_ready()

    assert "EOD_S3_BUCKET" in str(excinfo.value)


def test_production_s3_configuration_accepts_bucket_without_credentials() -> None:
    Settings(
        environment="production",
        database_url="sqlite:///ops.db",
        raj_agent_token="agent-token",  # noqa: S106 - test credential
        raj_dashboard_token="dashboard-token",  # noqa: S106 - test credential
        eod_storage_backend="s3",
        eod_s3_bucket="algo-eod",
    ).assert_production_ready()
