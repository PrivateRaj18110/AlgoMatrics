import time

from algo_platform.shared.infrastructure.security import (
    Totp,
    generate_api_key,
    generate_opaque_token,
    hash_password,
    hash_token,
    verify_password,
)


def test_password_hash_roundtrip() -> None:
    encoded = hash_password("Str0ng-Passw0rd!")
    assert encoded.startswith("scrypt$")
    assert verify_password("Str0ng-Passw0rd!", encoded)
    assert not verify_password("wrong-password", encoded)


def test_password_hashes_are_salted() -> None:
    assert hash_password("SamePass123") != hash_password("SamePass123")


def test_verify_password_handles_garbage() -> None:
    assert not verify_password("anything", "not-a-valid-hash")
    assert not verify_password("anything", "")


def test_opaque_tokens_are_unique_and_hashable() -> None:
    a, b = generate_opaque_token(), generate_opaque_token()
    assert a != b
    assert len(hash_token(a)) == 64
    assert hash_token(a) == hash_token(a)


def test_api_key_format() -> None:
    full, prefix, key_hash = generate_api_key()
    assert full.startswith("amk_")
    assert full.startswith(prefix[:4])
    assert key_hash == hash_token(full)


def test_totp_verify_accepts_current_and_adjacent_windows() -> None:
    secret = Totp.generate_secret()
    totp = Totp(secret)
    now = time.time()
    code = totp.code_at(now)
    assert totp.verify(code, at=now)
    assert totp.verify(totp.code_at(now - 30), at=now)
    assert totp.verify(totp.code_at(now + 30), at=now)
    assert not totp.verify(totp.code_at(now - 120), at=now)
    assert not totp.verify("000000" if code != "000000" else "111111", at=now)


def test_totp_provisioning_uri() -> None:
    secret = Totp.generate_secret()
    uri = Totp(secret).provisioning_uri(account_name="a@b.co", issuer="Algo Matrics")
    assert uri.startswith("otpauth://totp/")
    assert "issuer=Algo+Matrics" in uri
    assert f"secret={secret}" in uri
