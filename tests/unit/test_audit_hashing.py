"""Unit tests for the tamper-evident audit hash chain (Phase 3, slice A)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from algo_platform.modules.audit.application.hashing import (
    GENESIS_HASH,
    AuditFacts,
    ChainedEntry,
    compute_entry_hash,
    verify_chain,
)


def _facts(seq: int, **over: object) -> AuditFacts:
    base = AuditFacts(
        sequence=seq,
        occurred_at=datetime(2026, 7, 8, 12, 0, seq, tzinfo=UTC),
        action="user.login",
        resource_type="session",
        resource_id="s1",
        actor_type="user",
        actor_user_id=uuid4(),
        organization_id=uuid4(),
        request_id="req",
        correlation_id="corr",
        session_id="sess",
        ip_hash="iphash",
        before_state=None,
        after_state={"ok": True},
    )
    return replace(base, **over)  # type: ignore[arg-type]


def _build_chain(n: int) -> list[ChainedEntry]:
    entries: list[ChainedEntry] = []
    prev = GENESIS_HASH
    for i in range(1, n + 1):
        facts = _facts(i)
        entry_hash = compute_entry_hash(prev, facts)
        entries.append(ChainedEntry(facts=facts, prev_hash=prev, entry_hash=entry_hash))
        prev = entry_hash
    return entries


def test_hash_is_deterministic() -> None:
    facts = _facts(1)
    assert compute_entry_hash(GENESIS_HASH, facts) == compute_entry_hash(GENESIS_HASH, facts)


def test_hash_changes_with_any_field() -> None:
    base = _facts(1)
    h = compute_entry_hash(GENESIS_HASH, base)
    assert compute_entry_hash(GENESIS_HASH, replace(base, action="user.logout")) != h
    assert compute_entry_hash(GENESIS_HASH, replace(base, after_state={"ok": False})) != h
    assert compute_entry_hash("deadbeef", base) != h  # different predecessor


def test_intact_chain_verifies() -> None:
    assert verify_chain(_build_chain(5)) is None


def test_tampered_payload_is_detected() -> None:
    chain = _build_chain(5)
    # An attacker edits entry 3's stored facts but cannot recompute later hashes.
    tampered = chain[2]
    chain[2] = ChainedEntry(
        facts=replace(tampered.facts, after_state={"ok": False}),
        prev_hash=tampered.prev_hash,
        entry_hash=tampered.entry_hash,
    )
    assert verify_chain(chain) == 3


def test_broken_link_is_detected() -> None:
    chain = _build_chain(4)
    bad = chain[2]
    chain[2] = ChainedEntry(facts=bad.facts, prev_hash="0" * 64, entry_hash=bad.entry_hash)
    assert verify_chain(chain) == 3


def test_deleted_entry_is_detected() -> None:
    chain = _build_chain(4)
    del chain[1]  # remove sequence 2; the link from 1 -> 3 is now broken
    assert verify_chain(chain) == 3
