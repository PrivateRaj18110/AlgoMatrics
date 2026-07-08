"""Audit trail: immutable, tamper-evident actor/action evidence.

Writes are chained with SHA-256 (see :mod:`.hashing`). To keep the chain
consistent under concurrency, each write takes a transaction-scoped Postgres
advisory lock so exactly one audit insert computes the "previous" hash at a
time. Audit volume is low relative to trading traffic, so this global
serialization is an acceptable cost for a verifiable, append-only log.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.audit.application.hashing import (
    GENESIS_HASH,
    AuditFacts,
    ChainedEntry,
    compute_entry_hash,
    verify_chain,
)
from algo_platform.modules.audit.infrastructure.models import AuditLogModel
from algo_platform.shared.domain.types import utc_now

# Fixed key for pg_advisory_xact_lock; serializes audit-chain appends.
_AUDIT_ADVISORY_LOCK_KEY = 0x41444954  # "ADIT"


@dataclass(frozen=True, slots=True)
class AuditEntryDTO:
    id: UUID
    organization_id: UUID | None
    actor_user_id: UUID | None
    actor_type: str
    action: str
    resource_type: str
    resource_id: str
    request_id: str | None
    correlation_id: str | None
    session_id: str | None
    before_state: dict[str, Any] | None
    after_state: dict[str, Any] | None
    sequence: int | None
    entry_hash: str | None
    occurred_at: datetime


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str = "",
        organization_id: UUID | None = None,
        actor_user_id: UUID | None = None,
        actor_type: str = "user",
        request_id: str | None = None,
        correlation_id: str | None = None,
        session_id: str | None = None,
        ip_hash: str | None = None,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
    ) -> None:
        # Serialize chain appends for the remainder of the transaction.
        await self._session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": _AUDIT_ADVISORY_LOCK_KEY}
        )
        last = (
            await self._session.execute(
                select(AuditLogModel)
                .order_by(AuditLogModel.sequence.desc().nullslast())
                .limit(1)
            )
        ).scalars().first()
        prev_hash = last.entry_hash if last and last.entry_hash else GENESIS_HASH
        sequence = (last.sequence + 1) if last and last.sequence is not None else 1
        occurred_at = utc_now()
        facts = AuditFacts(
            sequence=sequence,
            occurred_at=occurred_at,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            actor_type=actor_type,
            actor_user_id=actor_user_id,
            organization_id=organization_id,
            request_id=request_id,
            correlation_id=correlation_id,
            session_id=session_id,
            ip_hash=ip_hash,
            before_state=before_state,
            after_state=after_state,
        )
        entry_hash = compute_entry_hash(prev_hash, facts)
        self._session.add(
            AuditLogModel(
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                actor_type=actor_type,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                request_id=request_id,
                correlation_id=correlation_id,
                session_id=session_id,
                ip_hash=ip_hash,
                before_state=before_state,
                after_state=after_state,
                sequence=sequence,
                prev_hash=prev_hash,
                entry_hash=entry_hash,
                occurred_at=occurred_at,
            )
        )

    async def search(
        self,
        *,
        organization_id: UUID | None,
        action_prefix: str | None = None,
        actor_user_id: UUID | None = None,
        correlation_id: str | None = None,
        resource_type: str | None = None,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AuditEntryDTO], int]:
        stmt = select(AuditLogModel)
        count_stmt = select(func.count()).select_from(AuditLogModel)

        def _apply(query: Any) -> Any:
            if organization_id is not None:
                query = query.where(AuditLogModel.organization_id == organization_id)
            if action_prefix:
                query = query.where(AuditLogModel.action.startswith(action_prefix))
            if actor_user_id is not None:
                query = query.where(AuditLogModel.actor_user_id == actor_user_id)
            if correlation_id:
                query = query.where(AuditLogModel.correlation_id == correlation_id)
            if resource_type:
                query = query.where(AuditLogModel.resource_type == resource_type)
            if occurred_from is not None:
                query = query.where(AuditLogModel.occurred_at >= occurred_from)
            if occurred_to is not None:
                query = query.where(AuditLogModel.occurred_at <= occurred_to)
            return query

        stmt = _apply(stmt).order_by(AuditLogModel.occurred_at.desc()).limit(limit).offset(offset)
        rows = (await self._session.execute(stmt)).scalars().all()
        total = int((await self._session.execute(_apply(count_stmt))).scalar_one())
        return ([_to_dto(r) for r in rows], total)

    async def verify_integrity(self, *, limit: int = 10_000) -> AuditIntegrityReport:
        """Recompute the hash chain over the most recent ``limit`` entries.

        Returns whether the chain is intact and, if not, the sequence of the
        first tampered entry.
        """
        rows = (
            await self._session.execute(
                select(AuditLogModel)
                .where(AuditLogModel.sequence.is_not(None))
                .order_by(AuditLogModel.sequence.desc())
                .limit(limit)
            )
        ).scalars().all()
        ordered = list(reversed(rows))
        if not ordered:
            return AuditIntegrityReport(checked=0, intact=True, first_bad_sequence=None)
        first = ordered[0]
        start_prev = first.prev_hash or GENESIS_HASH
        chain = [
            ChainedEntry(facts=_to_facts(r), prev_hash=r.prev_hash, entry_hash=r.entry_hash)
            for r in ordered
        ]
        bad = verify_chain(chain, start_prev=start_prev)
        return AuditIntegrityReport(
            checked=len(ordered), intact=bad is None, first_bad_sequence=bad
        )


@dataclass(frozen=True, slots=True)
class AuditIntegrityReport:
    checked: int
    intact: bool
    first_bad_sequence: int | None


def _to_facts(row: AuditLogModel) -> AuditFacts:
    return AuditFacts(
        sequence=row.sequence if row.sequence is not None else 0,
        occurred_at=row.occurred_at,
        action=row.action,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        actor_type=row.actor_type,
        actor_user_id=row.actor_user_id,
        organization_id=row.organization_id,
        request_id=row.request_id,
        correlation_id=row.correlation_id,
        session_id=row.session_id,
        ip_hash=row.ip_hash,
        before_state=row.before_state,
        after_state=row.after_state,
    )


def _to_dto(row: AuditLogModel) -> AuditEntryDTO:
    return AuditEntryDTO(
        id=row.id,
        organization_id=row.organization_id,
        actor_user_id=row.actor_user_id,
        actor_type=row.actor_type,
        action=row.action,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        request_id=row.request_id,
        correlation_id=row.correlation_id,
        session_id=row.session_id,
        before_state=row.before_state,
        after_state=row.after_state,
        sequence=row.sequence,
        entry_hash=row.entry_hash,
        occurred_at=row.occurred_at,
    )
