from uuid import UUID

import pytest

from algo_platform.modules.brokerage.infrastructure.verifiers import Mt5AgentVerifier
from algo_platform.modules.trading.infrastructure.brokers.indian import VenueInstrument
from algo_platform.modules.trading.infrastructure.brokers.mt5 import (
    Mt5AgentExecutionAdapter,
)
from algo_platform.shared.domain.errors import ConflictError


@pytest.mark.asyncio
async def test_mt5_verifier_requires_https_when_configured() -> None:
    verifier = Mt5AgentVerifier(
        allowed_hosts=frozenset({"agent.example.com"}),
        require_https=True,
    )

    result = await verifier.verify(
        {"agent_url": "http://agent.example.com:9100", "agent_token": "secret"}
    )

    assert not result.ok
    assert "HTTPS" in result.message


@pytest.mark.asyncio
async def test_mt5_verifier_rejects_non_allowlisted_host_before_network() -> None:
    verifier = Mt5AgentVerifier(
        allowed_hosts=frozenset({"agent.example.com"}),
        require_https=True,
    )

    result = await verifier.verify(
        {"agent_url": "https://169.254.169.254/latest/meta-data", "agent_token": "secret"}
    )

    assert not result.ok
    assert "allowlist" in result.message


def test_mt5_execution_adapter_rechecks_allowlist() -> None:
    async def resolver(_instrument_id: UUID) -> VenueInstrument:
        raise AssertionError("not called")

    with pytest.raises(ConflictError, match="allowlist"):
        Mt5AgentExecutionAdapter(
            agent_url="https://169.254.169.254",
            agent_token="secret",
            symbol_resolver=resolver,
            allowed_hosts=frozenset({"agent.example.com"}),
            require_https=True,
        )
