"""The monitoring.v1 contract, as the receiver sees it.

The contract is owned by the **LLS producer**. This module reads the published
schema and enforces the normative rules that JSON Schema cannot express. It
never redefines anything: where the receiver and the contract disagree, the
contract wins and the receiver is wrong.

Three rules from the contract document drive most of this file:

* ``message_id`` is a **content address** — ``mon1/`` followed by the SHA-256 of
  the canonical JSON of the message with ``message_id`` removed. The receiver can
  therefore verify identity itself rather than trusting the sender's label.
* The request digest in ``X-Monitoring-SHA256`` covers the **whole request body
  bytes**. Not a sub-object.
* Unsupported versions are **quarantined, never guessed at**.

Fail-closed: if the schema cannot be loaded, the receiver cannot validate, and a
receiver that cannot validate must not accept anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from app.core.config import get_settings

#: The only wire version this build implements. The contract states the version
#: identifies *field meaning*, not merely shape, so this is an exact match and
#: never a range.
MONITORING_SCHEMA_VERSION = "monitoring.v1"

#: Prefix of a monitoring.v1 content-addressed message identity.
MESSAGE_ID_PREFIX = "mon1/"


class ContractUnavailable(RuntimeError):
    """The published schema could not be loaded."""


@dataclass(frozen=True, slots=True)
class Limits:
    """Normative limits from the schema ``$comment`` and the contract document.

    None of these are expressible in JSON Schema, so they are enforced here. The
    values are the producer's stated defaults; a receiver that allowed more would
    accept messages the producer will never send and would mask a producer bug.
    """

    request_bytes: int = 1_048_576
    array_items: int = 100
    depth: int = 24
    nodes: int = 30_000
    string_chars: int = 4_096


LIMITS = Limits()


@dataclass(frozen=True, slots=True)
class VersionDecision:
    """What to do with a message, based on its declared ``schema_version``."""

    raw: str
    #: "accept" | "quarantine"
    action: str
    reason: str | None = None
    note: str | None = None

    @property
    def accepted(self) -> bool:
        return self.action == "accept"


@dataclass(frozen=True, slots=True)
class StructuralViolation:
    """A normative limit the message breaches."""

    reason: str
    detail: str


def schema_dir() -> Path:
    """Directory holding the canonical monitoring.v1 schema."""
    configured = (get_settings().monitoring_schema_dir or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    # ops/backend/app/monitoring/contract.py -> repository root
    return (Path(__file__).resolve().parents[4] / "schemas" / "monitoring-v1").resolve()


@lru_cache(maxsize=1)
def _schema_document() -> dict[str, Any]:
    directory = schema_dir()
    path = directory / "monitoring.v1.schema.json"
    if not path.is_file():
        raise ContractUnavailable(
            f"monitoring.v1 schema not found at {path}. "
            "Set MONITORING_SCHEMA_DIR to the published contract directory. "
            "The receiver refuses to accept data it cannot validate."
        )
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - corrupt install
        raise ContractUnavailable(f"{path.name} is not valid JSON: {exc}") from exc
    declared = document.get("properties", {}).get("schema_version", {}).get("const")
    if declared != MONITORING_SCHEMA_VERSION:
        raise ContractUnavailable(
            f"{path.name} declares schema_version const {declared!r}; "
            f"this build implements {MONITORING_SCHEMA_VERSION!r} and cannot validate it"
        )
    return document


@lru_cache(maxsize=1)
def message_validator() -> Draft202012Validator:
    """Validator for one monitoring.v1 message."""
    return Draft202012Validator(_schema_document())


def contract_available() -> bool:
    """True when the canonical schema is loadable — used by the health probe."""
    try:
        _schema_document()
    except ContractUnavailable:
        return False
    return True


def reset_cache() -> None:
    """Drop the cached schema. Tests use this after pointing at another dir."""
    _schema_document.cache_clear()
    message_validator.cache_clear()


# --------------------------------------------------------------------------- #
# Canonical serialisation
# --------------------------------------------------------------------------- #
def canonical_json(value: Any) -> bytes:
    """Deterministic JSON encoding shared with the LLS producer.

    Verified byte-identical against real producer fixtures: UTF-8, object keys
    sorted, no insignificant whitespace, non-ASCII left unescaped. This algorithm
    predates the contract reconciliation and survived it unchanged — it was the
    one thing both sides had already agreed on.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def request_digest(raw_body: bytes) -> str:
    """SHA-256 over the whole request body, per the contract.

    The superseded receiver hashed only a sub-object. That scope was wrong and is
    not retained: a digest that does not cover the bytes on the wire cannot
    detect a truncated or tampered request.
    """
    return hashlib.sha256(raw_body).hexdigest()


def message_identity(document: dict[str, Any]) -> str:
    """The content address a conforming message must carry as ``message_id``.

    ``mon1/`` + SHA-256 of the canonical JSON of the message with ``message_id``
    removed. Because it is derived, the receiver verifies it rather than trusting
    the label — a message whose body was altered in transit cannot keep a valid
    identity.
    """
    without_id = {key: value for key, value in document.items() if key != "message_id"}
    return MESSAGE_ID_PREFIX + hashlib.sha256(canonical_json(without_id)).hexdigest()


def identity_matches(document: dict[str, Any]) -> bool:
    """True when the declared ``message_id`` equals the computed content address."""
    declared = document.get("message_id")
    if not isinstance(declared, str):
        return False
    return declared == message_identity(document)


# --------------------------------------------------------------------------- #
# Version policy
# --------------------------------------------------------------------------- #
def classify_version(raw: Any) -> VersionDecision:
    """Decide how to treat a declared ``schema_version``.

    The contract is explicit: receivers quarantine unsupported versions rather
    than guessing. The version identifies field *meaning*, so there is no
    forward-compatible reading of an unknown one — a ``monitoring.v2`` message
    may reuse field names to mean different things.
    """
    if not isinstance(raw, str) or not raw:
        return VersionDecision(raw=str(raw), action="quarantine", reason="schema_version_missing")
    if raw != MONITORING_SCHEMA_VERSION:
        return VersionDecision(
            raw=raw,
            action="quarantine",
            reason="schema_version_unsupported",
            note=f"receiver implements {MONITORING_SCHEMA_VERSION}",
        )
    return VersionDecision(raw=raw, action="accept")


# --------------------------------------------------------------------------- #
# Parsing and structural limits
# --------------------------------------------------------------------------- #
class DuplicateKeyError(ValueError):
    """The message contains a duplicate object key."""


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise DuplicateKeyError(f"duplicate key {key!r}")
        seen[key] = value
    return seen


def _reject_non_finite(token: str) -> Any:
    raise ValueError(f"non-finite number {token!r}")


def parse_message(raw_body: bytes) -> dict[str, Any]:
    """Parse a request body under the contract's parsing rules.

    Duplicate keys and non-finite numbers are rejected at parse time rather than
    normalised away, because both change meaning silently: ``json.loads`` would
    otherwise keep the last duplicate and happily produce ``Infinity``.
    """
    text = raw_body.decode("utf-8")
    return json.loads(text, object_pairs_hook=_reject_duplicates, parse_constant=_reject_non_finite)


def check_limits(document: Any, raw_body: bytes | None = None) -> StructuralViolation | None:
    """Enforce the normative limits. Returns the first violation, or None."""
    if raw_body is not None and len(raw_body) > LIMITS.request_bytes:
        return StructuralViolation(
            reason="request_too_large",
            detail=f"{len(raw_body)} bytes exceeds the {LIMITS.request_bytes} byte limit",
        )

    nodes = 0

    def walk(node: Any, depth: int) -> StructuralViolation | None:
        nonlocal nodes
        nodes += 1
        if nodes > LIMITS.nodes:
            return StructuralViolation(
                reason="too_many_nodes", detail=f"more than {LIMITS.nodes} nodes"
            )
        if depth > LIMITS.depth:
            return StructuralViolation(
                reason="excessive_nesting", detail=f"deeper than {LIMITS.depth} levels"
            )
        if isinstance(node, dict):
            for value in node.values():
                violation = walk(value, depth + 1)
                if violation is not None:
                    return violation
        elif isinstance(node, list):
            if len(node) > LIMITS.array_items:
                return StructuralViolation(
                    reason="array_too_long",
                    detail=f"{len(node)} elements exceeds {LIMITS.array_items}",
                )
            for value in node:
                violation = walk(value, depth + 1)
                if violation is not None:
                    return violation
        elif isinstance(node, str):
            if len(node) > LIMITS.string_chars:
                return StructuralViolation(
                    reason="string_too_long",
                    detail=f"{len(node)} characters exceeds {LIMITS.string_chars}",
                )
        elif isinstance(node, float) and not math.isfinite(node):
            return StructuralViolation(reason="non_finite_number", detail=repr(node))
        return None

    return walk(document, 1)


def schema_errors(document: dict[str, Any]) -> list[str]:
    """Schema violations, most specific first. Empty means the message conforms."""
    errors = sorted(message_validator().iter_errors(document), key=str)
    return [
        f"{'/'.join(str(part) for part in error.path) or '$'}: {error.message}" for error in errors
    ]


# --------------------------------------------------------------------------- #
# Sequence
# --------------------------------------------------------------------------- #
def parse_sequence(raw: Any) -> int | None:
    """``source_sequence`` is a decimal **string** starting at 1.

    Returned as an int for ordering arithmetic only. The original string is
    preserved verbatim in evidence and echoed in the acknowledgement — the
    contract's ACK carries ``source_sequence`` as a string, and a receiver that
    re-rendered it would fail the sender's identity check.
    """
    if not isinstance(raw, str) or not raw.isdigit() or raw.startswith("0"):
        return None
    return int(raw)
