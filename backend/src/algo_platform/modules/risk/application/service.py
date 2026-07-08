"""Risk services: pre-trade policy, limits CRUD, kill switches, violations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.risk.domain.limits import (
    KillSwitch,
    KillSwitchScope,
    RiskDecision,
    RiskDecisionResult,
    RiskLimits,
)
from algo_platform.modules.risk.infrastructure.models import (
    KillSwitchModel,
    RiskDecisionModel,
    RiskEventModel,
    RiskLimitsModel,
)
from algo_platform.shared.domain.errors import ConflictError, NotFoundError
from algo_platform.shared.domain.types import AccountId, TenantId, UserId, utc_now

logger = structlog.get_logger(__name__)

POLICY_VERSION = 1


@dataclass(frozen=True, slots=True)
class OrderRiskInput:
    """Snapshot of state the policy evaluates; assembled by the caller."""

    organization_id: TenantId
    account_id: AccountId
    order_id: UUID
    quantity: Decimal
    estimated_price: Decimal
    orders_today: int
    max_orders_per_day: int
    realized_pnl_today: Decimal
    open_positions: int
    gross_exposure: Decimal
    account_equity: Decimal
    account_starting_balance: Decimal


@dataclass(frozen=True, slots=True)
class RiskLimitsDTO:
    id: UUID
    account_id: UUID | None
    max_order_quantity: Decimal
    max_order_value: Decimal
    max_daily_loss: Decimal
    max_open_positions: int
    max_exposure_value: Decimal
    max_drawdown_pct: Decimal
    is_active: bool
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class KillSwitchDTO:
    id: UUID
    scope: str
    scope_ref: str
    reason: str
    engaged_by: UUID
    engaged_at: datetime
    released_at: datetime | None


@dataclass(frozen=True, slots=True)
class RiskEventDTO:
    id: UUID
    account_id: UUID | None
    strategy_run_id: UUID | None
    event_type: str
    severity: str
    message: str
    details: dict[str, Any]
    occurred_at: datetime


def _limits_to_entity(model: RiskLimitsModel) -> RiskLimits:
    return RiskLimits(
        id=model.id,
        organization_id=TenantId(model.organization_id),
        account_id=AccountId(model.account_id) if model.account_id else None,
        max_order_quantity=model.max_order_quantity,
        max_order_value=model.max_order_value,
        max_daily_loss=model.max_daily_loss,
        max_open_positions=model.max_open_positions,
        max_exposure_value=model.max_exposure_value,
        max_drawdown_pct=model.max_drawdown_pct,
        is_active=model.is_active,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


class RiskService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -- limits ------------------------------------------------------------

    async def get_effective_limits(
        self, organization_id: TenantId, account_id: AccountId | None = None
    ) -> RiskLimits:
        if account_id is not None:
            result = await self._session.execute(
                select(RiskLimitsModel).where(
                    RiskLimitsModel.organization_id == organization_id,
                    RiskLimitsModel.account_id == account_id,
                    RiskLimitsModel.is_active,
                )
            )
            model = result.scalar_one_or_none()
            if model is not None:
                return _limits_to_entity(model)
        result = await self._session.execute(
            select(RiskLimitsModel).where(
                RiskLimitsModel.organization_id == organization_id,
                RiskLimitsModel.account_id.is_(None),
            )
        )
        model = result.scalar_one_or_none()
        if model is not None:
            return _limits_to_entity(model)
        # First touch: persist defaults so the org always has an editable row.
        limits = RiskLimits.defaults(organization_id=organization_id)
        self._session.add(
            RiskLimitsModel(
                id=limits.id,
                organization_id=limits.organization_id,
                account_id=None,
                max_order_quantity=limits.max_order_quantity,
                max_order_value=limits.max_order_value,
                max_daily_loss=limits.max_daily_loss,
                max_open_positions=limits.max_open_positions,
                max_exposure_value=limits.max_exposure_value,
                max_drawdown_pct=limits.max_drawdown_pct,
                is_active=True,
                created_at=limits.created_at,
                updated_at=limits.updated_at,
            )
        )
        await self._session.flush()
        return limits

    async def list_limits(self, organization_id: TenantId) -> list[RiskLimitsDTO]:
        await self.get_effective_limits(organization_id)
        result = await self._session.execute(
            select(RiskLimitsModel)
            .where(RiskLimitsModel.organization_id == organization_id)
            .order_by(RiskLimitsModel.account_id.nulls_first())
        )
        return [
            RiskLimitsDTO(
                id=m.id,
                account_id=m.account_id,
                max_order_quantity=m.max_order_quantity,
                max_order_value=m.max_order_value,
                max_daily_loss=m.max_daily_loss,
                max_open_positions=m.max_open_positions,
                max_exposure_value=m.max_exposure_value,
                max_drawdown_pct=m.max_drawdown_pct,
                is_active=m.is_active,
                updated_at=m.updated_at,
            )
            for m in result.scalars().all()
        ]

    async def update_limits(
        self,
        organization_id: TenantId,
        limits_id: UUID,
        changes: dict[str, Any],
    ) -> RiskLimitsDTO:
        model = await self._session.get(RiskLimitsModel, limits_id)
        if model is None or model.organization_id != organization_id:
            raise NotFoundError("risk limits not found")
        entity = _limits_to_entity(model)
        entity.update(changes)
        model.max_order_quantity = entity.max_order_quantity
        model.max_order_value = entity.max_order_value
        model.max_daily_loss = entity.max_daily_loss
        model.max_open_positions = entity.max_open_positions
        model.max_exposure_value = entity.max_exposure_value
        model.max_drawdown_pct = entity.max_drawdown_pct
        model.is_active = entity.is_active
        model.updated_at = utc_now()
        await self._session.flush()
        return RiskLimitsDTO(
            id=model.id,
            account_id=model.account_id,
            max_order_quantity=model.max_order_quantity,
            max_order_value=model.max_order_value,
            max_daily_loss=model.max_daily_loss,
            max_open_positions=model.max_open_positions,
            max_exposure_value=model.max_exposure_value,
            max_drawdown_pct=model.max_drawdown_pct,
            is_active=model.is_active,
            updated_at=model.updated_at,
        )

    # -- kill switches --------------------------------------------------------

    async def active_kill_switch(
        self,
        organization_id: TenantId,
        *,
        account_id: AccountId | None = None,
        strategy_run_id: UUID | None = None,
    ) -> KillSwitchModel | None:
        conditions = [
            (KillSwitchScope.ORGANIZATION.value, ""),
        ]
        if account_id is not None:
            conditions.append((KillSwitchScope.ACCOUNT.value, str(account_id)))
        if strategy_run_id is not None:
            conditions.append((KillSwitchScope.STRATEGY.value, str(strategy_run_id)))
        for scope, ref in conditions:
            stmt = select(KillSwitchModel).where(
                KillSwitchModel.organization_id == organization_id,
                KillSwitchModel.scope == scope,
                KillSwitchModel.released_at.is_(None),
            )
            if ref:
                stmt = stmt.where(KillSwitchModel.scope_ref == ref)
            result = await self._session.execute(stmt.limit(1))
            model = result.scalars().first()
            if model is not None:
                return model
        return None

    async def engage_kill_switch(
        self,
        organization_id: TenantId,
        *,
        scope: KillSwitchScope,
        scope_ref: str,
        reason: str,
        engaged_by: UserId,
    ) -> KillSwitchDTO:
        existing = await self._session.execute(
            select(KillSwitchModel).where(
                KillSwitchModel.organization_id == organization_id,
                KillSwitchModel.scope == scope.value,
                KillSwitchModel.scope_ref == scope_ref,
                KillSwitchModel.released_at.is_(None),
            )
        )
        if existing.scalars().first() is not None:
            raise ConflictError("a kill switch is already engaged for this scope")
        switch = KillSwitch.engage(
            organization_id=organization_id,
            scope=scope,
            scope_ref=scope_ref,
            reason=reason,
            engaged_by=engaged_by,
        )
        self._session.add(
            KillSwitchModel(
                id=switch.id,
                organization_id=switch.organization_id,
                scope=switch.scope.value,
                scope_ref=switch.scope_ref,
                reason=switch.reason,
                engaged_by=switch.engaged_by,
                engaged_at=switch.engaged_at,
            )
        )
        await self._session.flush()
        await self.record_event(
            organization_id,
            event_type="kill_switch_engaged",
            severity="critical",
            message=f"kill switch engaged ({switch.scope.value}): {switch.reason}",
            details={"scope": switch.scope.value, "scope_ref": switch.scope_ref},
        )
        return self._switch_dto(switch.id, switch)

    async def release_kill_switch(
        self, organization_id: TenantId, switch_id: UUID, *, released_by: UserId
    ) -> None:
        model = await self._session.get(KillSwitchModel, switch_id)
        if model is None or model.organization_id != organization_id:
            raise NotFoundError("kill switch not found")
        if model.released_at is not None:
            raise ConflictError("kill switch is already released")
        model.released_at = utc_now()
        model.released_by = released_by
        await self._session.flush()
        await self.record_event(
            organization_id,
            event_type="kill_switch_released",
            severity="info",
            message=f"kill switch released ({model.scope})",
            details={"scope": model.scope, "scope_ref": model.scope_ref},
        )

    async def list_kill_switches(
        self, organization_id: TenantId, *, include_released: bool = False
    ) -> list[KillSwitchDTO]:
        stmt = select(KillSwitchModel).where(KillSwitchModel.organization_id == organization_id)
        if not include_released:
            stmt = stmt.where(KillSwitchModel.released_at.is_(None))
        stmt = stmt.order_by(KillSwitchModel.engaged_at.desc()).limit(100)
        result = await self._session.execute(stmt)
        return [
            KillSwitchDTO(
                id=m.id,
                scope=m.scope,
                scope_ref=m.scope_ref,
                reason=m.reason,
                engaged_by=m.engaged_by,
                engaged_at=m.engaged_at,
                released_at=m.released_at,
            )
            for m in result.scalars().all()
        ]

    @staticmethod
    def _switch_dto(switch_id: UUID, switch: KillSwitch) -> KillSwitchDTO:
        return KillSwitchDTO(
            id=switch_id,
            scope=switch.scope.value,
            scope_ref=switch.scope_ref,
            reason=switch.reason,
            engaged_by=switch.engaged_by,
            engaged_at=switch.engaged_at,
            released_at=switch.released_at,
        )

    # -- pre-trade policy ----------------------------------------------------------

    async def evaluate_order(self, order_input: OrderRiskInput) -> RiskDecision:
        """Fail-closed pre-trade gate. Every decision is persisted as evidence."""
        limits = await self.get_effective_limits(
            order_input.organization_id, order_input.account_id
        )
        reasons: list[str] = []

        switch = await self.active_kill_switch(
            order_input.organization_id, account_id=order_input.account_id
        )
        if switch is not None:
            reasons.append("kill_switch_engaged")

        if order_input.quantity > limits.max_order_quantity:
            reasons.append("max_order_quantity_exceeded")
        order_value = order_input.quantity * order_input.estimated_price
        if order_value > limits.max_order_value:
            reasons.append("max_order_value_exceeded")
        if (
            order_input.max_orders_per_day >= 0
            and order_input.orders_today >= order_input.max_orders_per_day
        ):
            reasons.append("plan_daily_order_limit_reached")
        if order_input.realized_pnl_today <= -limits.max_daily_loss:
            reasons.append("max_daily_loss_breached")
        if order_input.open_positions >= limits.max_open_positions:
            reasons.append("max_open_positions_reached")
        if order_input.gross_exposure + order_value > limits.max_exposure_value:
            reasons.append("max_exposure_exceeded")
        if order_input.account_starting_balance > 0:
            drawdown_pct = (
                (order_input.account_starting_balance - order_input.account_equity)
                / order_input.account_starting_balance
                * 100
            )
            if drawdown_pct >= limits.max_drawdown_pct:
                reasons.append("max_drawdown_breached")

        result = RiskDecisionResult.REJECTED if reasons else RiskDecisionResult.APPROVED
        decision = RiskDecision.make(
            organization_id=order_input.organization_id,
            order_id=order_input.order_id,
            result=result,
            reason_codes=reasons,
            inputs={
                "quantity": str(order_input.quantity),
                "estimated_price": str(order_input.estimated_price),
                "order_value": str(order_value),
                "orders_today": order_input.orders_today,
                "realized_pnl_today": str(order_input.realized_pnl_today),
                "open_positions": order_input.open_positions,
                "gross_exposure": str(order_input.gross_exposure),
                "account_equity": str(order_input.account_equity),
            },
            policy_version=POLICY_VERSION,
        )
        self._session.add(
            RiskDecisionModel(
                id=decision.id,
                organization_id=decision.organization_id,
                order_id=decision.order_id,
                result=decision.result.value,
                reason_codes=list(decision.reason_codes),
                inputs=dict(decision.inputs),
                policy_version=decision.policy_version,
                decided_at=decision.decided_at,
            )
        )
        await self._session.flush()
        if reasons:
            await self.record_event(
                order_input.organization_id,
                account_id=order_input.account_id,
                event_type="order_rejected",
                severity="warning",
                message="pre-trade risk rejected an order: " + ", ".join(reasons),
                details={"order_id": str(order_input.order_id), "reasons": reasons},
            )
        return decision

    # -- events -------------------------------------------------------------------------

    async def record_event(
        self,
        organization_id: TenantId,
        *,
        event_type: str,
        severity: str,
        message: str,
        details: dict[str, Any] | None = None,
        account_id: AccountId | None = None,
        strategy_run_id: UUID | None = None,
    ) -> None:
        self._session.add(
            RiskEventModel(
                organization_id=organization_id,
                account_id=account_id,
                strategy_run_id=strategy_run_id,
                event_type=event_type,
                severity=severity,
                message=message[:500],
                details=details or {},
                occurred_at=utc_now(),
            )
        )
        await self._session.flush()

    async def list_events(
        self,
        organization_id: TenantId,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[RiskEventDTO], int]:
        stmt = (
            select(RiskEventModel)
            .where(RiskEventModel.organization_id == organization_id)
            .order_by(RiskEventModel.occurred_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        total = int(
            (
                await self._session.execute(
                    select(func.count())
                    .select_from(RiskEventModel)
                    .where(RiskEventModel.organization_id == organization_id)
                )
            ).scalar_one()
        )
        return (
            [
                RiskEventDTO(
                    id=r.id,
                    account_id=r.account_id,
                    strategy_run_id=r.strategy_run_id,
                    event_type=r.event_type,
                    severity=r.severity,
                    message=r.message,
                    details=dict(r.details),
                    occurred_at=r.occurred_at,
                )
                for r in rows
            ],
            total,
        )
