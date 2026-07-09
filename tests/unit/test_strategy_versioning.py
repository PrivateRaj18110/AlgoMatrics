"""Unit tests for strategy versioning (Phase 14, slice A)."""

from __future__ import annotations

import pytest

from algo_platform.modules.strategies.domain.versioning import (
    ApprovalAction,
    ApprovalStatus,
    SemanticVersion,
    diff_versions,
    transition,
    validate_manifest,
)
from algo_platform.shared.domain.errors import ConflictError, ValidationFailed


def test_semver_parse_and_str() -> None:
    v = SemanticVersion.parse("1.2.3")
    assert (v.major, v.minor, v.patch) == (1, 2, 3)
    assert str(v) == "1.2.3"


def test_semver_rejects_garbage() -> None:
    for bad in ["1.2", "v1.2.3", "1.2.3.4", "a.b.c", ""]:
        with pytest.raises(ValidationFailed):
            SemanticVersion.parse(bad)


def test_semver_ordering_and_bumps() -> None:
    assert SemanticVersion.parse("1.0.0") < SemanticVersion.parse("1.0.1")
    assert SemanticVersion.parse("1.2.0") < SemanticVersion.parse("2.0.0")
    assert str(SemanticVersion(1, 2, 3).bump_major()) == "2.0.0"
    assert str(SemanticVersion(1, 2, 3).bump_minor()) == "1.3.0"
    assert str(SemanticVersion(1, 2, 3).bump_patch()) == "1.2.4"


def _manifest(entry: str, params: list[dict], checksum: str = "c") -> dict:
    return {"entry_point": entry, "parameters": params, "checksum": checksum}


def test_diff_detects_added_removed_changed() -> None:
    old = _manifest("x", [{"name": "fast", "type": "int", "default": 5}, {"name": "gone"}])
    new = _manifest(
        "x", [{"name": "fast", "type": "int", "default": 10}, {"name": "slow"}]
    )
    diff = diff_versions(old, new)
    assert diff.added_parameters == ["slow"]
    assert diff.removed_parameters == ["gone"]
    assert [c.name for c in diff.changed_parameters] == ["fast"]
    assert diff.has_changes


def test_diff_suggested_bump() -> None:
    base = _manifest("x", [{"name": "a"}])
    assert not diff_versions(base, base).has_changes
    assert diff_versions(base, base).suggested_bump() == "patch"
    # Added param -> minor
    added = diff_versions(base, _manifest("x", [{"name": "a"}, {"name": "b"}]))
    assert added.suggested_bump() == "minor"
    # Removed param -> major (breaking)
    removed = diff_versions(base, _manifest("x", []))
    assert removed.suggested_bump() == "major"
    # Entry point change -> major
    entry = diff_versions(base, _manifest("y", [{"name": "a"}]))
    assert entry.entry_point_changed and entry.suggested_bump() == "major"


def test_validate_manifest() -> None:
    assert validate_manifest(_manifest("x", [{"name": "a"}])) == []
    assert "entry_point is required" in validate_manifest(_manifest("", [{"name": "a"}]))
    dup = validate_manifest(_manifest("x", [{"name": "a"}, {"name": "a"}]))
    assert any("duplicate" in i for i in dup)
    rng = validate_manifest(_manifest("x", [{"name": "a", "min": 10, "max": 1}]))
    assert any("min exceeds max" in i for i in rng)


def test_approval_happy_path() -> None:
    s = ApprovalStatus.DRAFT
    s = transition(s, ApprovalAction.SUBMIT)
    assert s is ApprovalStatus.PENDING_REVIEW
    s = transition(s, ApprovalAction.APPROVE)
    assert s is ApprovalStatus.APPROVED


def test_approval_reject_then_resubmit() -> None:
    s = transition(ApprovalStatus.PENDING_REVIEW, ApprovalAction.REJECT)
    assert s is ApprovalStatus.REJECTED
    assert transition(s, ApprovalAction.SUBMIT) is ApprovalStatus.PENDING_REVIEW


def test_approval_withdraw() -> None:
    assert (
        transition(ApprovalStatus.PENDING_REVIEW, ApprovalAction.WITHDRAW)
        is ApprovalStatus.DRAFT
    )


def test_illegal_transitions_raise() -> None:
    with pytest.raises(ConflictError):
        transition(ApprovalStatus.APPROVED, ApprovalAction.APPROVE)
    with pytest.raises(ConflictError):
        transition(ApprovalStatus.DRAFT, ApprovalAction.APPROVE)
