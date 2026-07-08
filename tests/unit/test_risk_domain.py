"""Domain tests for the risk aggregate: limits, kill switches, decisions."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from algo_platform.modules.risk.domain.limits import (
    DEFAULT_MAX_ORDER_QUANTITY,
    KillSwitch,
    KillSwitchScope,
    RiskDecision,
    RiskDecisionResult,
    RiskLimits,
)
from algo_platform.shared.domain.errors import ConflictError, ValidationFailed
from algo_platform.shared.domain.types import TenantId, UserId


class TestRiskLimits:
    def _limits(self) -> RiskLimits:
        return RiskLimits.defaults(organization_id=TenantId(uuid4()))

    def test_defaults(self) -> None:
        limits = self._limits()
        assert limits.max_order_quantity == DEFAULT_MAX_ORDER_QUANTITY
        assert limits.account_id is None
        assert limits.is_active

    def test_update_decimal_fields(self) -> None:
        limits = self._limits()
        limits.update({"max_order_value": "500", "max_drawdown_pct": 10})
        assert limits.max_order_value == Decimal("500")
        assert limits.max_drawdown_pct == Decimal("10")

    def test_non_positive_decimal_rejected(self) -> None:
        with pytest.raises(ValidationFailed, match="must be positive"):
            self._limits().update({"max_order_value": "0"})

    def test_open_positions_bounds(self) -> None:
        limits = self._limits()
        limits.update({"max_open_positions": 50})
        assert limits.max_open_positions == 50
        with pytest.raises(ValidationFailed, match="1-10000"):
            limits.update({"max_open_positions": 0})
        with pytest.raises(ValidationFailed, match="1-10000"):
            limits.update({"max_open_positions": 20_000})

    def test_is_active_toggle(self) -> None:
        limits = self._limits()
        limits.update({"is_active": False})
        assert not limits.is_active

    def test_unknown_field_rejected(self) -> None:
        with pytest.raises(ValidationFailed, match="unknown risk limit field"):
            self._limits().update({"bogus": 1})


class TestKillSwitch:
    def _switch(self) -> KillSwitch:
        return KillSwitch.engage(
            organization_id=TenantId(uuid4()),
            scope=KillSwitchScope.ORGANIZATION,
            scope_ref="org",
            reason="  runaway strategy  ",
            engaged_by=UserId(uuid4()),
        )

    def test_engage_trims_reason(self) -> None:
        switch = self._switch()
        assert switch.reason == "runaway strategy"
        assert switch.is_engaged

    def test_empty_reason_rejected(self) -> None:
        with pytest.raises(ValidationFailed, match="reason is required"):
            KillSwitch.engage(
                organization_id=TenantId(uuid4()),
                scope=KillSwitchScope.ACCOUNT,
                scope_ref="acct",
                reason="   ",
                engaged_by=UserId(uuid4()),
            )

    def test_release_once(self) -> None:
        switch = self._switch()
        releaser = UserId(uuid4())
        switch.release(releaser)
        assert not switch.is_engaged
        assert switch.released_by == releaser
        with pytest.raises(ConflictError, match="already released"):
            switch.release(releaser)


class TestRiskDecision:
    def test_make_records_inputs(self) -> None:
        decision = RiskDecision.make(
            organization_id=TenantId(uuid4()),
            order_id=uuid4(),
            result=RiskDecisionResult.REJECTED,
            reason_codes=["max_order_value_exceeded"],
            inputs={"order_value": "1000000"},
        )
        assert decision.result is RiskDecisionResult.REJECTED
        assert decision.reason_codes == ["max_order_value_exceeded"]
        assert decision.policy_version == 1
