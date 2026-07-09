"""Encrypted-file secrets backend for local development.

Secrets are stored as a Fernet-encrypted JSON document on disk, so a developer
can keep real credentials in the repo working tree without committing plaintext.
The Fernet key is supplied out of band (env var or a key file kept outside the
repo). Decryption happens once and is cached for the process lifetime.

Use ``python -m algo_platform.scripts.secrets_cli`` to generate a key and to
encrypt/decrypt the document.
"""

from __future__ import annotations

import json
from pathlib import Path

from cryptography.fernet import Fernet


class EncryptedFileSecretsProvider:
    def __init__(self, *, path: Path | None, key: str) -> None:
        if path is None:
            raise ValueError("encrypted secrets backend requires SECRETS_ENCRYPTED_FILE")
        self._path = Path(path)
        # Fernet validates the key shape (32-byte urlsafe base64) here.
        self._fernet = Fernet(key.encode("utf-8"))
        self._cache: dict[str, str] | None = None

    def _load(self) -> dict[str, str]:
        if self._cache is None:
            token = self._path.read_bytes()
            data = json.loads(self._fernet.decrypt(token))
            if not isinstance(data, dict):
                raise ValueError("encrypted secret document is not a JSON object")
            self._cache = {str(k): str(v) for k, v in data.items()}
        return self._cache

    def get(self, name: str) -> str | None:
        value = self._load().get(name)
        return value if value else None
