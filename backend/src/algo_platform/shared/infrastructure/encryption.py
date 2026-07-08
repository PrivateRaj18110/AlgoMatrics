"""Envelope encryption for broker credentials and other secrets at rest.

Each record gets a fresh 256-bit data-encryption key (DEK) used with
AES-256-GCM. The DEK is wrapped by the key-encryption key (KEK) supplied via
configuration (file or environment; a cloud KMS can replace the KEK source
without touching call sites). Ciphertext, nonces, and the wrapped DEK are
stored base64-encoded. The associated data (AAD) binds ciphertext to its
owning record so values cannot be swapped between rows.
"""

from __future__ import annotations

import base64
import binascii
import secrets
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from algo_platform.shared.domain.errors import InvariantViolation

_NONCE_BYTES = 12
_KEY_BYTES = 32


class DecryptionFailed(InvariantViolation):
    pass


@dataclass(frozen=True, slots=True)
class EncryptedSecret:
    ciphertext_b64: str
    wrapped_dek_b64: str
    key_version: int


class CredentialCipher:
    def __init__(self, kek: bytes, *, key_version: int = 1) -> None:
        if len(kek) != _KEY_BYTES:
            raise ValueError("KEK must be exactly 32 bytes")
        self._kek = AESGCM(kek)
        self._key_version = key_version

    @classmethod
    def from_base64(cls, kek_b64: str, *, key_version: int = 1) -> CredentialCipher:
        try:
            kek = base64.b64decode(kek_b64, validate=True)
        except (binascii.Error, ValueError) as error:
            raise ValueError("KEK must be valid base64") from error
        return cls(kek, key_version=key_version)

    @staticmethod
    def generate_kek_b64() -> str:
        return base64.b64encode(secrets.token_bytes(_KEY_BYTES)).decode("ascii")

    def encrypt(self, plaintext: bytes, *, aad: bytes) -> EncryptedSecret:
        dek_bytes = secrets.token_bytes(_KEY_BYTES)
        data_nonce = secrets.token_bytes(_NONCE_BYTES)
        ciphertext = AESGCM(dek_bytes).encrypt(data_nonce, plaintext, aad)
        wrap_nonce = secrets.token_bytes(_NONCE_BYTES)
        wrapped = self._kek.encrypt(wrap_nonce, dek_bytes, aad)
        return EncryptedSecret(
            ciphertext_b64=base64.b64encode(data_nonce + ciphertext).decode("ascii"),
            wrapped_dek_b64=base64.b64encode(wrap_nonce + wrapped).decode("ascii"),
            key_version=self._key_version,
        )

    def decrypt(self, secret: EncryptedSecret, *, aad: bytes) -> bytes:
        try:
            wrapped_blob = base64.b64decode(secret.wrapped_dek_b64)
            dek_bytes = self._kek.decrypt(
                wrapped_blob[:_NONCE_BYTES], wrapped_blob[_NONCE_BYTES:], aad
            )
            data_blob = base64.b64decode(secret.ciphertext_b64)
            return AESGCM(dek_bytes).decrypt(
                data_blob[:_NONCE_BYTES], data_blob[_NONCE_BYTES:], aad
            )
        except (InvalidTag, ValueError, binascii.Error) as error:
            raise DecryptionFailed("credential decryption failed") from error
