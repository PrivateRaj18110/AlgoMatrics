from uuid import uuid4

import pytest

from algo_platform.modules.strategies.builtin.registry import (
    BUILTIN_MANIFESTS,
    create_builtin,
    is_builtin,
)
from algo_platform.modules.strategies.domain.strategies import (
    ParameterSpec,
    RunState,
    StrategyRun,
    StrategyVersion,
    VersionSource,
)
from algo_platform.modules.strategies.infrastructure.artifact_store import (
    validate_strategy_source,
)
from algo_platform.shared.domain.errors import (
    InvariantViolation,
    ValidationFailed,
)
from algo_platform.shared.domain.types import AccountId, TenantId, UserId


def make_run() -> StrategyRun:
    return StrategyRun.create(
        organization_id=TenantId(uuid4()),
        strategy_id=uuid4(),
        strategy_version_id=uuid4(),
        account_id=AccountId(uuid4()),
        mode="paper",
        parameters={},
        instrument_ids=[uuid4()],
        timeframe="1m",
        created_by=UserId(uuid4()),
    )


class TestRunStateMachine:
    def test_happy_path(self) -> None:
        run = make_run()
        assert run.state is RunState.PENDING
        run.request_start()
        assert run.state is RunState.STARTING
        run.mark_running()
        assert run.state is RunState.RUNNING
        run.pause()
        assert run.state is RunState.PAUSED
        run.mark_running()
        run.request_stop()
        assert run.state is RunState.STOPPING
        run.mark_stopped()
        assert run.state is RunState.STOPPED
        assert not run.is_active

    def test_cannot_pause_when_not_running(self) -> None:
        run = make_run()
        with pytest.raises(InvariantViolation):
            run.pause()

    def test_failure_records_error(self) -> None:
        run = make_run()
        run.request_start()
        run.mark_failed("boom")
        assert run.state is RunState.FAILED
        assert run.error == "boom"
        run.request_start()  # restart after failure is allowed
        assert run.state is RunState.STARTING

    def test_run_validation(self) -> None:
        with pytest.raises(ValidationFailed, match="at least one instrument"):
            StrategyRun.create(
                organization_id=TenantId(uuid4()),
                strategy_id=uuid4(),
                strategy_version_id=uuid4(),
                account_id=AccountId(uuid4()),
                mode="paper",
                parameters={},
                instrument_ids=[],
                timeframe="1m",
                created_by=UserId(uuid4()),
            )


class TestParameters:
    def test_spec_coercion_and_bounds(self) -> None:
        spec = ParameterSpec(name="period", type="int", default=14, minimum=2, maximum=100)
        assert spec.validate_value("21") == 21
        with pytest.raises(ValidationFailed):
            spec.validate_value(1)
        with pytest.raises(ValidationFailed):
            spec.validate_value("abc")

    def test_version_resolves_defaults_and_rejects_unknown(self) -> None:
        version = StrategyVersion(
            id=uuid4(),
            strategy_id=uuid4(),
            organization_id=TenantId(uuid4()),
            version=1,
            source=VersionSource.BUILTIN,
            entry_point="x",
            artifact_path=None,
            checksum="builtin",
            manifest={
                "parameters": [
                    {"name": "fast", "type": "int", "default": 9, "min": 2, "max": 50},
                    {"name": "allow_short", "type": "bool", "default": False},
                ]
            },
        )
        resolved = version.resolve_parameters({"fast": 12})
        assert resolved == {"fast": 12, "allow_short": False}
        with pytest.raises(ValidationFailed, match="unknown parameters"):
            version.resolve_parameters({"nope": 1})


class TestBuiltinRegistry:
    def test_manifests_are_complete(self) -> None:
        assert len(BUILTIN_MANIFESTS) == 3
        for entry_point, manifest in BUILTIN_MANIFESTS.items():
            assert is_builtin(entry_point)
            assert manifest["name"]
            assert manifest["parameters"]
            instance = create_builtin(entry_point)
            assert instance is not None

    def test_unknown_builtin_raises(self) -> None:
        with pytest.raises(LookupError):
            create_builtin("does:NotExist")


VALID_SOURCE = """
from decimal import Decimal

from algo_strategy_sdk.context import StrategyContext
from algo_strategy_sdk.events import Candle
from algo_strategy_sdk.strategy import Strategy


class MyStrategy(Strategy):
    async def on_candle(self, candle: Candle, context: StrategyContext) -> None:
        if candle.close > Decimal("100"):
            await context.request_order(
                instrument=candle.instrument, side="buy", quantity=Decimal("1")
            )
"""


class TestArtifactValidation:
    def test_valid_source_accepted(self) -> None:
        validated = validate_strategy_source(VALID_SOURCE, entry_class="MyStrategy")
        assert validated.class_name == "MyStrategy"
        assert len(validated.checksum) == 64

    def test_missing_entry_class_rejected(self) -> None:
        with pytest.raises(ValidationFailed, match="entry class"):
            validate_strategy_source(VALID_SOURCE, entry_class="Other")

    def test_forbidden_import_rejected(self) -> None:
        bad = "import os\n" + VALID_SOURCE
        with pytest.raises(ValidationFailed, match="may not import 'os'"):
            validate_strategy_source(bad, entry_class="MyStrategy")

    def test_network_import_rejected(self) -> None:
        bad = "import httpx\n" + VALID_SOURCE
        with pytest.raises(ValidationFailed, match="may not import 'httpx'"):
            validate_strategy_source(bad, entry_class="MyStrategy")

    def test_forbidden_call_rejected(self) -> None:
        bad = VALID_SOURCE + "\nsecret = eval('1+1')\n"
        with pytest.raises(ValidationFailed, match="may not call 'eval'"):
            validate_strategy_source(bad, entry_class="MyStrategy")

    def test_dunder_access_rejected(self) -> None:
        bad = VALID_SOURCE + "\nx = Strategy.__subclasses__\n"
        with pytest.raises(ValidationFailed, match="dunder"):
            validate_strategy_source(bad, entry_class="MyStrategy")

    def test_syntax_error_rejected(self) -> None:
        with pytest.raises(ValidationFailed, match="syntax error"):
            validate_strategy_source("def broken(:", entry_class="X")
