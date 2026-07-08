"""Password hashing, opaque token handling, and RFC 6238 TOTP.

Passwords use scrypt (memory-hard, stdlib) with per-hash random salt.
Opaque tokens (refresh, e-mail, API keys) are high-entropy random values;
only their SHA-256 digest is stored at rest.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
import urllib.parse

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 64
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return "scrypt${}${}${}${}${}".format(
        _SCRYPT_N,
        _SCRYPT_R,
        _SCRYPT_P,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n_s, r_s, p_s, salt_b64, digest_b64 = encoded.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        candidate = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n_s),
            r=int(r_s),
            p=int(p_s),
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, expected)


def generate_opaque_token(entropy_bytes: int = 48) -> str:
    return secrets.token_urlsafe(entropy_bytes)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def generate_api_key() -> tuple[str, str, str]:
    """Return (full_key, prefix, key_hash). Only hash and prefix are persisted."""
    raw = secrets.token_urlsafe(36)
    full = f"amk_{raw}"
    return full, full[:12], hash_token(full)


class Totp:
    """RFC 6238 TOTP (SHA-1, 6 digits, 30 s period) for authenticator apps."""

    period_seconds = 30
    digits = 6

    def __init__(self, secret_base32: str) -> None:
        self._secret = base64.b32decode(secret_base32.upper() + "=" * (-len(secret_base32) % 8))
        self._secret_base32 = secret_base32

    @classmethod
    def generate_secret(cls) -> str:
        return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")

    def code_at(self, timestamp: float) -> str:
        counter = int(timestamp) // self.period_seconds
        message = struct.pack(">Q", counter)
        digest = hmac.new(self._secret, message, hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        (value,) = struct.unpack(">I", digest[offset : offset + 4])
        value &= 0x7FFFFFFF
        return str(value % (10**self.digits)).zfill(self.digits)

    def verify(self, code: str, *, at: float | None = None, window: int = 1) -> bool:
        now = time.time() if at is None else at
        normalized = code.strip().replace(" ", "")
        return any(
            hmac.compare_digest(self.code_at(now + step * self.period_seconds), normalized)
            for step in range(-window, window + 1)
        )

    def provisioning_uri(self, *, account_name: str, issuer: str) -> str:
        label = urllib.parse.quote(f"{issuer}:{account_name}")
        query = urllib.parse.urlencode(
            {
                "secret": self._secret_base32,
                "issuer": issuer,
                "algorithm": "SHA1",
                "digits": str(self.digits),
                "period": str(self.period_seconds),
            }
        )
        return f"otpauth://totp/{label}?{query}"
