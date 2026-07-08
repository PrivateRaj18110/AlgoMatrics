"""Unit tests for the encrypted-file secrets backend + CLI (Phase 2, slice C)."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from algo_platform.scripts.secrets_cli import (
    decrypt_document,
    encrypt_document,
    generate_key,
    main,
)
from algo_platform.shared.infrastructure.secrets.encrypted import EncryptedFileSecretsProvider


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    # The default pytest tmp_path base is not writable in this environment; use a
    # repo-local, gitignored temp directory instead.
    base = Path("var") / "test-tmp"
    base.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(dir=base))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_encrypt_decrypt_roundtrip() -> None:
    key = generate_key()
    doc = {"jwt_private_key": "PRIV", "broker_credential_kek": "KEK"}
    token = encrypt_document(doc, key)
    assert token != str(doc).encode()  # actually encrypted
    assert decrypt_document(token, key) == doc


def test_provider_reads_encrypted_document(tmp_path: Path) -> None:
    key = generate_key()
    enc = tmp_path / "secrets.enc"
    enc.write_bytes(encrypt_document({"stripe_secret_key": "sk-live"}, key))
    provider = EncryptedFileSecretsProvider(path=enc, key=key)
    assert provider.get("stripe_secret_key") == "sk-live"
    assert provider.get("absent") is None


def test_provider_rejects_missing_path() -> None:
    with pytest.raises(ValueError, match="SECRETS_ENCRYPTED_FILE"):
        EncryptedFileSecretsProvider(path=None, key=generate_key())


def test_provider_rejects_wrong_key(tmp_path: Path) -> None:
    enc = tmp_path / "secrets.enc"
    enc.write_bytes(encrypt_document({"a": "b"}, generate_key()))
    provider = EncryptedFileSecretsProvider(path=enc, key=Fernet.generate_key().decode())
    with pytest.raises(Exception):  # noqa: B017 - cryptography InvalidToken
        provider.get("a")


def test_cli_keygen_encrypt_decrypt(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    key = generate_key()
    plain = tmp_path / "plain.json"
    plain.write_text('{"jwt_private_key": "PRIV"}', encoding="utf-8")
    enc = tmp_path / "out.enc"

    assert main(["--key", key, "encrypt", "--in", str(plain), "--out", str(enc)]) == 0
    assert enc.exists()

    assert main(["--key", key, "decrypt", "--in", str(enc)]) == 0
    out = capsys.readouterr().out
    assert '"jwt_private_key": "PRIV"' in out


def test_cli_missing_key_exits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECRETS_ENCRYPTION_KEY", raising=False)
    plain = tmp_path / "p.json"
    plain.write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit):
        main(["encrypt", "--in", str(plain), "--out", str(tmp_path / "o.enc")])
