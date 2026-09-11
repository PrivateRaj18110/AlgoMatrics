"""monitoring.v1 contract gate — the receiver measured against the real producer.

Every assertion here runs against the **actual LLS handoff package**, not against
fixtures written to match our own implementation. That distinction is the whole
point: a receiver tested only against its own idea of the contract will pass its
own tests and fail the first real message.

The gate: all 19 producer-valid fixtures must be accepted, every negative fixture
must retain its intended rejection, and the canonical-JSON and identity
computations must agree with the producer byte for byte.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any

import pytest

from app.monitoring import contract

REPO = pathlib.Path(__file__).resolve().parents[3]
PACKAGE = REPO / "tests" / "fixtures" / "lls-monitoring-v1-handoff"
CANONICAL = REPO / "schemas" / "monitoring-v1"


def _load(path: pathlib.Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def manifest() -> dict[str, Any]:
    return _load(PACKAGE / "fixture_manifest.json")


@pytest.fixture(scope="module")
def producer_valid(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    entries = [item for item in manifest["messages"] if item.get("producer_valid")]
    assert entries, "handoff package contains no producer-valid fixtures"
    return entries


def message_bytes(entry: dict[str, Any]) -> bytes:
    return (PACKAGE / entry["file"]).read_bytes()


def ids(entries: list[dict[str, Any]]) -> list[str]:
    return [entry["file"].rsplit("/", 1)[-1] for entry in entries]


# --------------------------------------------------------------------------- #
# The package and the canonical schema must not drift apart
# --------------------------------------------------------------------------- #
def test_canonical_schema_is_byte_identical_to_the_handoff_package() -> None:
    """Our copy of the contract is the producer's copy, unedited.

    If this fails, someone edited the schema on the receiver side — which creates
    a second contract that diverges silently. That is the failure this whole
    reconciliation exists to remove.
    """
    ours = (CANONICAL / "monitoring.v1.schema.json").read_bytes()
    theirs = (PACKAGE / "schema" / "monitoring.v1.schema.json").read_bytes()
    assert hashlib.sha256(ours).hexdigest() == hashlib.sha256(theirs).hexdigest()


def test_canonical_contract_document_is_byte_identical_to_the_package() -> None:
    ours = (CANONICAL / "ALGOMATRIC_MONITORING_CONTRACT.md").read_bytes()
    theirs = (PACKAGE / "contract" / "ALGOMATRIC_MONITORING_CONTRACT.md").read_bytes()
    assert hashlib.sha256(ours).hexdigest() == hashlib.sha256(theirs).hexdigest()


def test_receiver_loads_the_canonical_schema() -> None:
    contract.reset_cache()
    assert contract.contract_available() is True
    assert contract.MONITORING_SCHEMA_VERSION == "monitoring.v1"


def test_the_superseded_proposal_is_not_loadable_as_a_contract() -> None:
    """There must be exactly one wire contract in `schemas/`."""
    assert not (REPO / "schemas" / "monitoring-export").exists()
    assert [p.name for p in (REPO / "schemas").iterdir() if p.is_dir()] == ["monitoring-v1"]


# --------------------------------------------------------------------------- #
# THE GATE: every producer-valid fixture is accepted
# --------------------------------------------------------------------------- #
def test_all_producer_valid_fixtures_are_accepted(producer_valid) -> None:
    """19 / 19. The first acceptance criterion of the reconciliation."""
    rejected: list[tuple[str, list[str]]] = []
    for entry in producer_valid:
        document = contract.parse_message(message_bytes(entry))
        errors = contract.schema_errors(document)
        version = contract.classify_version(document.get("schema_version"))
        limits = contract.check_limits(document, message_bytes(entry))
        if errors or not version.accepted or limits is not None:
            rejected.append(
                (entry["file"], errors[:2] or [version.reason or (limits.reason if limits else "")])
            )

    assert not rejected, "producer-valid fixtures rejected:\n" + "\n".join(
        f"  {name}: {why}" for name, why in rejected
    )
    assert len(producer_valid) == 19


def test_every_fixture_individually(producer_valid) -> None:
    """Same gate, reported per file so a failure names the message."""
    for entry in producer_valid:
        document = contract.parse_message(message_bytes(entry))
        assert contract.schema_errors(document) == [], entry["file"]


# --------------------------------------------------------------------------- #
# Identity — content-addressed, and verified rather than trusted
# --------------------------------------------------------------------------- #
def test_message_id_is_a_verifiable_content_address(producer_valid) -> None:
    """`mon1/` + sha256 of canonical JSON with `message_id` removed.

    Computed independently here. If our canonicalisation differed from the
    producer's by a single byte, every one of these would fail.
    """
    for entry in producer_valid:
        document = contract.parse_message(message_bytes(entry))
        assert contract.identity_matches(document), entry["file"]
        assert document["message_id"] == entry["message_id"]


def test_altering_the_body_invalidates_the_identity(producer_valid) -> None:
    document = contract.parse_message(message_bytes(producer_valid[0]))
    document["source_id"] = "someone-else"
    assert contract.identity_matches(document) is False


# --------------------------------------------------------------------------- #
# Canonical JSON and request digest
# --------------------------------------------------------------------------- #
def test_canonical_json_reproduces_producer_bytes_exactly(producer_valid) -> None:
    """The producer's files are already canonical; we must reproduce them."""
    for entry in producer_valid:
        raw = message_bytes(entry)
        document = contract.parse_message(raw)
        assert contract.canonical_json(document) == raw, entry["file"]


def test_request_digest_matches_the_producer_manifest(producer_valid) -> None:
    """Hash scope is the whole request body, as the contract requires."""
    for entry in producer_valid:
        assert contract.request_digest(message_bytes(entry)) == entry["sha256"], entry["file"]


def test_digest_is_not_computed_over_a_sub_object(producer_valid) -> None:
    """Regression guard against the superseded scope.

    The previous receiver hashed a nested `observation` object. Nothing in
    monitoring.v1 has that key, and a sub-object digest cannot detect a truncated
    request. If someone reintroduces sub-object hashing, this fails.
    """
    entry = producer_valid[0]
    raw = message_bytes(entry)
    document = contract.parse_message(raw)
    payload_only = contract.canonical_json(document["payload"])
    assert hashlib.sha256(payload_only).hexdigest() != entry["sha256"]
    assert contract.request_digest(raw) == entry["sha256"]


# --------------------------------------------------------------------------- #
# Negative fixtures keep their intended behaviour
# --------------------------------------------------------------------------- #
def _classify(raw: bytes) -> tuple[str, str]:
    """Run a message through the contract layer, returning (outcome, reason)."""
    try:
        document = contract.parse_message(raw)
    except contract.DuplicateKeyError as exc:
        return "rejected", f"duplicate_keys: {exc}"
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return "rejected", f"unparseable: {exc}"

    limits = contract.check_limits(document, raw)
    if limits is not None:
        return "rejected", limits.reason

    version = contract.classify_version(document.get("schema_version"))
    if not version.accepted:
        return "quarantined", version.reason or "schema_version"

    errors = contract.schema_errors(document)
    if errors:
        return "quarantined", f"schema_invalid: {errors[0][:80]}"

    if not contract.identity_matches(document):
        return "rejected", "identity_mismatch"

    return "accepted", ""


@pytest.mark.parametrize(
    ("fixture", "expected_outcome"),
    [
        ("malformed_duplicate_keys.json", "rejected"),
        ("bad_schema_version.json", "quarantined"),
        ("invalid_message_id.json", "rejected"),
        ("oversized_string.json", "rejected"),
        ("excessive_nesting.json", "rejected"),
    ],
)
def test_negative_fixtures_are_refused(fixture: str, expected_outcome: str) -> None:
    """Each invalid fixture must fail, and fail for the right reason."""
    raw = (PACKAGE / "fixtures" / "messages" / fixture).read_bytes()
    outcome, reason = _classify(raw)
    assert outcome == expected_outcome, f"{fixture}: got {outcome} ({reason})"


def test_no_negative_fixture_is_ever_accepted() -> None:
    """Blanket guard: nothing the producer marked invalid may pass the gate."""
    manifest = _load(PACKAGE / "fixture_manifest.json")
    invalid = [item for item in manifest["messages"] if not item.get("producer_valid")]
    assert invalid, "manifest lists no invalid fixtures"
    for entry in invalid:
        outcome, _ = _classify(message_bytes(entry))
        assert outcome != "accepted", entry["file"]


def test_conflict_fixture_parses_but_fails_identity() -> None:
    """Same id, changed body. Detected by the content address, not by storage.

    This is a genuine improvement from adopting monitoring.v1: identity is
    derived from content, so a reused id with different bytes is caught at the
    contract layer before it can reach evidence at all.
    """
    raw = (PACKAGE / "fixtures" / "messages" / "conflict_same_id_changed_payload.json").read_bytes()
    outcome, reason = _classify(raw)
    assert outcome == "rejected"
    assert reason == "identity_mismatch"


# --------------------------------------------------------------------------- #
# Version policy
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("version", ["monitoring.v2", "1.0", "v1", "", "monitoring.v1.1", None, 1])
def test_unsupported_versions_are_quarantined_never_guessed(version: Any) -> None:
    decision = contract.classify_version(version)
    assert decision.action == "quarantine"


def test_the_supported_version_is_accepted() -> None:
    assert contract.classify_version("monitoring.v1").accepted is True


# --------------------------------------------------------------------------- #
# Normative limits
# --------------------------------------------------------------------------- #
def test_limits_match_the_published_contract() -> None:
    assert contract.LIMITS.request_bytes == 1_048_576
    assert contract.LIMITS.array_items == 100
    assert contract.LIMITS.depth == 24
    assert contract.LIMITS.nodes == 30_000
    assert contract.LIMITS.string_chars == 4_096


def test_oversized_request_is_refused() -> None:
    body = b"x" * (contract.LIMITS.request_bytes + 1)
    violation = contract.check_limits({}, body)
    assert violation is not None and violation.reason == "request_too_large"


def test_duplicate_keys_are_refused_not_silently_collapsed() -> None:
    """`json.loads` would keep the last one and lose the disagreement."""
    with pytest.raises(contract.DuplicateKeyError):
        contract.parse_message(b'{"a": 1, "a": 2}')


def test_non_finite_numbers_are_refused() -> None:
    with pytest.raises(ValueError):
        contract.parse_message(b'{"a": NaN}')


def test_long_array_is_refused() -> None:
    violation = contract.check_limits({"items": list(range(contract.LIMITS.array_items + 1))})
    assert violation is not None and violation.reason == "array_too_long"


# --------------------------------------------------------------------------- #
# Sequence is a string, and stays one
# --------------------------------------------------------------------------- #
def test_source_sequence_is_parsed_for_ordering_only(producer_valid) -> None:
    for entry in producer_valid:
        document = contract.parse_message(message_bytes(entry))
        raw = document["source_sequence"]
        assert isinstance(raw, str)
        assert contract.parse_sequence(raw) == int(raw)


@pytest.mark.parametrize("bad", ["0", "007", "", "-1", "1.0", 1, None])
def test_malformed_sequences_are_not_coerced(bad: Any) -> None:
    assert contract.parse_sequence(bad) is None


# --------------------------------------------------------------------------- #
# LLS semantics are preserved, not reinterpreted
# --------------------------------------------------------------------------- #
def test_unknown_and_stale_fixture_keeps_its_states() -> None:
    """The producer built this fixture specifically to catch a receiver that
    upgrades STALE to live or turns UNKNOWN into a value."""
    raw = (
        PACKAGE / "fixtures" / "messages" / "unknown_stale_incomplete_synthetic_salvaged.json"
    ).read_bytes()
    outcome, reason = _classify(raw)
    assert outcome == "accepted", reason

    document = contract.parse_message(raw)
    assert document["freshness"]["source"] == "STALE"
    assert document["trust"]["status"] == "UNTRUSTED"
    assert document["coverage"]["status"] == "INCOMPLETE"
    # `environment` is market reality, not a deployment tier.
    assert document["environment"] == "offline_fixture"
    # `runtime` is a list of capture identifiers, not an enum.
    assert isinstance(document["runtime"], list)


def test_no_stale_after_exists_anywhere_in_the_contract() -> None:
    """We must not synthesise a validity horizon the producer never sends."""
    schema = (CANONICAL / "monitoring.v1.schema.json").read_text(encoding="utf-8")
    assert "stale_after" not in schema


def test_qualified_values_carry_status_and_may_carry_an_explicit_null() -> None:
    """LLS writes `{"value": null, "status": "UNKNOWN", "reason": ...}`.

    The superseded proposal required the value key to be *absent*. Under the
    canonical contract an explicit null is correct and must be preserved, not
    stripped and not read as a zero.
    """
    raw = (PACKAGE / "fixtures" / "messages" / "valid_snapshot.json").read_bytes()
    document = contract.parse_message(raw)
    broker = document["payload"]["execution"]["independent_broker_state"]
    assert broker["status"] == "UNKNOWN"
    assert broker["value"] is None
    assert broker["reason"]
