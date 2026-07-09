"""Strategy versioning: semantic versions, diff, validation, approval workflow.

Pure and framework-free so the rules are unit testable and reusable by the
service, API, and any future tooling. Complements the existing immutable
``StrategyVersion`` records rather than replacing them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from algo_platform.shared.domain.errors import ConflictError, ValidationFailed

_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


@dataclass(frozen=True, slots=True, order=True)
class SemanticVersion:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> SemanticVersion:
        match = _SEMVER.match(value.strip())
        if match is None:
            raise ValidationFailed(f"invalid semantic version: {value!r}")
        return cls(int(match[1]), int(match[2]), int(match[3]))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def bump_major(self) -> SemanticVersion:
        return SemanticVersion(self.major + 1, 0, 0)

    def bump_minor(self) -> SemanticVersion:
        return SemanticVersion(self.major, self.minor + 1, 0)

    def bump_patch(self) -> SemanticVersion:
        return SemanticVersion(self.major, self.minor, self.patch + 1)


# -- diff ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ParameterChange:
    name: str
    field: str
    old: Any
    new: Any


@dataclass(frozen=True, slots=True)
class VersionDiff:
    entry_point_changed: bool
    checksum_changed: bool
    added_parameters: list[str] = field(default_factory=list)
    removed_parameters: list[str] = field(default_factory=list)
    changed_parameters: list[ParameterChange] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return (
            self.entry_point_changed
            or self.checksum_changed
            or bool(self.added_parameters or self.removed_parameters or self.changed_parameters)
        )

    def suggested_bump(self) -> str:
        """major = breaking (removed/changed params or entry point), minor = added, patch = else."""
        if self.entry_point_changed or self.removed_parameters or self.changed_parameters:
            return "major"
        if self.added_parameters:
            return "minor"
        return "patch"


def _params_by_name(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(p["name"]): p for p in manifest.get("parameters", []) if "name" in p}


def diff_versions(old: dict[str, Any], new: dict[str, Any]) -> VersionDiff:
    old_params = _params_by_name(old)
    new_params = _params_by_name(new)
    added = sorted(set(new_params) - set(old_params))
    removed = sorted(set(old_params) - set(new_params))
    changed: list[ParameterChange] = []
    for name in sorted(set(old_params) & set(new_params)):
        for key in ("type", "default", "min", "max"):
            if old_params[name].get(key) != new_params[name].get(key):
                changed.append(
                    ParameterChange(
                        name=name,
                        field=key,
                        old=old_params[name].get(key),
                        new=new_params[name].get(key),
                    )
                )
    return VersionDiff(
        entry_point_changed=old.get("entry_point") != new.get("entry_point"),
        checksum_changed=old.get("checksum") != new.get("checksum"),
        added_parameters=added,
        removed_parameters=removed,
        changed_parameters=changed,
    )


# -- validation ------------------------------------------------------------


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    """Return a list of human-readable issues; empty means the manifest is valid."""
    issues: list[str] = []
    if not str(manifest.get("entry_point", "")).strip():
        issues.append("entry_point is required")
    seen: set[str] = set()
    for raw in manifest.get("parameters", []):
        name = str(raw.get("name", "")).strip()
        if not name:
            issues.append("a parameter is missing a name")
            continue
        if name in seen:
            issues.append(f"duplicate parameter '{name}'")
        seen.add(name)
        low, high = raw.get("min"), raw.get("max")
        if low is not None and high is not None and float(low) > float(high):
            issues.append(f"parameter '{name}': min exceeds max")
    return issues


# -- approval workflow -----------------------------------------------------


class ApprovalStatus(StrEnum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalAction(StrEnum):
    SUBMIT = "submit"
    APPROVE = "approve"
    REJECT = "reject"
    WITHDRAW = "withdraw"


_TRANSITIONS: dict[tuple[ApprovalStatus, ApprovalAction], ApprovalStatus] = {
    (ApprovalStatus.DRAFT, ApprovalAction.SUBMIT): ApprovalStatus.PENDING_REVIEW,
    (ApprovalStatus.PENDING_REVIEW, ApprovalAction.APPROVE): ApprovalStatus.APPROVED,
    (ApprovalStatus.PENDING_REVIEW, ApprovalAction.REJECT): ApprovalStatus.REJECTED,
    (ApprovalStatus.PENDING_REVIEW, ApprovalAction.WITHDRAW): ApprovalStatus.DRAFT,
    (ApprovalStatus.REJECTED, ApprovalAction.SUBMIT): ApprovalStatus.PENDING_REVIEW,
}


def transition(current: ApprovalStatus, action: ApprovalAction) -> ApprovalStatus:
    """Apply an approval action to a status, or raise if the transition is illegal."""
    nxt = _TRANSITIONS.get((current, action))
    if nxt is None:
        raise ConflictError(f"cannot {action.value} a version that is {current.value}")
    return nxt
