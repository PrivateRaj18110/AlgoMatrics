"""Strategy versioning service: approvals, diff, validation, deployment history."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.strategies.domain.versioning import (
    ApprovalAction,
    ApprovalStatus,
    VersionDiff,
    diff_versions,
    transition,
    validate_manifest,
)
from algo_platform.modules.strategies.infrastructure.models import (
    StrategyDeploymentModel,
    StrategyVersionApprovalModel,
    StrategyVersionModel,
)
from algo_platform.shared.domain.errors import NotFoundError
from algo_platform.shared.domain.types import TenantId, UserId, utc_now


@dataclass(frozen=True, slots=True)
class ApprovalDTO:
    version_id: UUID
    status: str
    review_note: str


class StrategyVersioningService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _version(self, organization_id: TenantId, version_id: UUID) -> StrategyVersionModel:
        model = await self._session.get(StrategyVersionModel, version_id)
        if model is None or model.organization_id != organization_id:
            raise NotFoundError("strategy version not found")
        return model

    async def _approval(self, version_id: UUID) -> StrategyVersionApprovalModel | None:
        return (
            await self._session.execute(
                select(StrategyVersionApprovalModel).where(
                    StrategyVersionApprovalModel.version_id == version_id
                )
            )
        ).scalars().first()

    async def status(self, organization_id: TenantId, version_id: UUID) -> ApprovalStatus:
        await self._version(organization_id, version_id)
        approval = await self._approval(version_id)
        return ApprovalStatus(approval.status) if approval else ApprovalStatus.DRAFT

    async def act(
        self,
        organization_id: TenantId,
        version_id: UUID,
        *,
        action: ApprovalAction,
        actor: UserId,
        note: str = "",
    ) -> ApprovalDTO:
        version = await self._version(organization_id, version_id)
        approval = await self._approval(version_id)
        current = ApprovalStatus(approval.status) if approval else ApprovalStatus.DRAFT
        new_status = transition(current, action)  # raises on illegal transition
        if approval is None:
            approval = StrategyVersionApprovalModel(
                version_id=version_id,
                organization_id=organization_id,
                status=new_status.value,
                submitted_by=actor,
                review_note=note[:1000],
                updated_at=utc_now(),
            )
            self._session.add(approval)
        else:
            approval.status = new_status.value
            approval.review_note = note[:1000]
            approval.updated_at = utc_now()
        if action in (ApprovalAction.APPROVE, ApprovalAction.REJECT):
            approval.reviewed_by = actor
        # Keep the immutable version's live flag in sync with approval outcome.
        version.approved_for_live = new_status is ApprovalStatus.APPROVED
        await self._session.flush()
        return ApprovalDTO(
            version_id=version_id, status=new_status.value, review_note=approval.review_note
        )

    async def validate(self, organization_id: TenantId, version_id: UUID) -> list[str]:
        version = await self._version(organization_id, version_id)
        return validate_manifest({**version.manifest, "entry_point": version.entry_point})

    async def diff(
        self, organization_id: TenantId, from_id: UUID, to_id: UUID
    ) -> VersionDiff:
        a = await self._version(organization_id, from_id)
        b = await self._version(organization_id, to_id)
        return diff_versions(_manifest(a), _manifest(b))

    async def record_deployment(
        self,
        organization_id: TenantId,
        *,
        version_id: UUID,
        actor: UserId,
        action: str = "deploy",
    ) -> None:
        version = await self._version(organization_id, version_id)
        self._session.add(
            StrategyDeploymentModel(
                strategy_id=version.strategy_id,
                organization_id=organization_id,
                version_id=version_id,
                version_label=str(version.version),
                action=action,
                deployed_by=actor,
                deployed_at=utc_now(),
            )
        )
        await self._session.flush()

    async def deployment_history(
        self, organization_id: TenantId, strategy_id: UUID, *, limit: int = 50
    ) -> list[dict[str, object]]:
        rows = (
            await self._session.execute(
                select(StrategyDeploymentModel)
                .where(
                    StrategyDeploymentModel.strategy_id == strategy_id,
                    StrategyDeploymentModel.organization_id == organization_id,
                )
                .order_by(StrategyDeploymentModel.deployed_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [
            {
                "version_id": str(r.version_id),
                "version": r.version_label,
                "action": r.action,
                "deployed_at": r.deployed_at.isoformat(),
            }
            for r in rows
        ]


def _manifest(version: StrategyVersionModel) -> dict[str, Any]:
    return {**version.manifest, "entry_point": version.entry_point, "checksum": version.checksum}
