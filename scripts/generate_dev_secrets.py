"""Generate local development secrets: RSA JWT keypair and broker KEK.

Writes files into ./secrets (git-ignored). Local/dev only — staging and
production must source secrets from a real secret manager, never from files
in the repository.
"""

from __future__ import annotations

import base64
import secrets as pysecrets
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

SECRETS_DIR = Path(__file__).resolve().parents[1] / "secrets"


def main() -> None:
    SECRETS_DIR.mkdir(exist_ok=True)
    private_path = SECRETS_DIR / "jwt_private.pem"
    public_path = SECRETS_DIR / "jwt_public.pem"
    kek_path = SECRETS_DIR / "broker_kek"

    if private_path.exists() and public_path.exists() and kek_path.exists():
        print(f"secrets already present in {SECRETS_DIR}; nothing to do")
        return

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    private_path.write_bytes(private_pem)
    public_path.write_bytes(public_pem)
    kek_path.write_text(
        base64.b64encode(pysecrets.token_bytes(32)).decode("ascii"), encoding="utf-8"
    )
    print(f"wrote {private_path.name}, {public_path.name}, {kek_path.name} to {SECRETS_DIR}")


if __name__ == "__main__":
    sys.exit(main())
