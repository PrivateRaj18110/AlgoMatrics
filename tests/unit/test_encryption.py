import pytest

from algo_platform.shared.infrastructure.encryption import (
    CredentialCipher,
    DecryptionFailed,
)


def test_envelope_roundtrip() -> None:
    cipher = CredentialCipher.from_base64(CredentialCipher.generate_kek_b64())
    secret = cipher.encrypt(b'{"api_key": "k"}', aad=b"conn:1")
    assert cipher.decrypt(secret, aad=b"conn:1") == b'{"api_key": "k"}'


def test_aad_binding_prevents_swaps() -> None:
    cipher = CredentialCipher.from_base64(CredentialCipher.generate_kek_b64())
    secret = cipher.encrypt(b"payload", aad=b"conn:1")
    with pytest.raises(DecryptionFailed):
        cipher.decrypt(secret, aad=b"conn:2")


def test_wrong_kek_fails() -> None:
    cipher_a = CredentialCipher.from_base64(CredentialCipher.generate_kek_b64())
    cipher_b = CredentialCipher.from_base64(CredentialCipher.generate_kek_b64())
    secret = cipher_a.encrypt(b"payload", aad=b"x")
    with pytest.raises(DecryptionFailed):
        cipher_b.decrypt(secret, aad=b"x")


def test_kek_must_be_32_bytes() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        CredentialCipher(b"short")


def test_unique_ciphertexts_per_encryption() -> None:
    cipher = CredentialCipher.from_base64(CredentialCipher.generate_kek_b64())
    first = cipher.encrypt(b"same", aad=b"a")
    second = cipher.encrypt(b"same", aad=b"a")
    assert first.ciphertext_b64 != second.ciphertext_b64
    assert first.wrapped_dek_b64 != second.wrapped_dek_b64
