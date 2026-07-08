"""CLI for the encrypted-file secrets backend (local development).

Examples::

    # 1. generate a key and keep it OUTSIDE the repo (e.g. export it)
    python -m algo_platform.scripts.secrets_cli keygen

    # 2. encrypt a plaintext JSON document of canonical secret names
    SECRETS_ENCRYPTION_KEY=... python -m algo_platform.scripts.secrets_cli \
        encrypt --in secrets.plain.json --out var/secrets.enc

    # 3. decrypt to edit
    SECRETS_ENCRYPTION_KEY=... python -m algo_platform.scripts.secrets_cli \
        decrypt --in var/secrets.enc

The plaintext document is a flat JSON object, e.g.::

    {"jwt_private_key": "-----BEGIN...", "broker_credential_kek": "base64=="}
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet

_KEY_ENV = "SECRETS_ENCRYPTION_KEY"


def generate_key() -> str:
    return Fernet.generate_key().decode("ascii")


def encrypt_document(document: dict[str, Any], key: str) -> bytes:
    payload = json.dumps(document, separators=(",", ":")).encode("utf-8")
    return Fernet(key.encode("utf-8")).encrypt(payload)


def decrypt_document(token: bytes, key: str) -> dict[str, Any]:
    data = json.loads(Fernet(key.encode("utf-8")).decrypt(token))
    if not isinstance(data, dict):
        raise ValueError("encrypted document is not a JSON object")
    return data


def _resolve_key(explicit: str | None) -> str:
    key = explicit or os.environ.get(_KEY_ENV)
    if not key:
        raise SystemExit(f"no key: pass --key or set {_KEY_ENV}")
    return key


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="secrets_cli", description=__doc__)
    parser.add_argument("--key", help=f"Fernet key (default: ${_KEY_ENV})")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("keygen", help="generate a new Fernet key")

    enc = sub.add_parser("encrypt", help="encrypt a plaintext JSON document")
    enc.add_argument("--in", dest="in_path", required=True, type=Path)
    enc.add_argument("--out", dest="out_path", required=True, type=Path)

    dec = sub.add_parser("decrypt", help="decrypt and print a JSON document")
    dec.add_argument("--in", dest="in_path", required=True, type=Path)

    args = parser.parse_args(argv)

    if args.command == "keygen":
        print(generate_key())
        return 0

    if args.command == "encrypt":
        document = json.loads(args.in_path.read_text(encoding="utf-8"))
        token = encrypt_document(document, _resolve_key(args.key))
        args.out_path.parent.mkdir(parents=True, exist_ok=True)
        args.out_path.write_bytes(token)
        print(f"wrote {args.out_path} ({len(document)} secrets)")
        return 0

    if args.command == "decrypt":
        document = decrypt_document(args.in_path.read_bytes(), _resolve_key(args.key))
        print(json.dumps(document, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
