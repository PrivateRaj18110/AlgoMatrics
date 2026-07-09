"""Unit tests for AI prompts, null provider, and factory (Phase 13, slice A)."""

from __future__ import annotations

import pytest

from algo_platform.modules.ai.application.ports import ChatMessage
from algo_platform.modules.ai.domain.prompts import (
    assistant_prompt,
    broker_diagnostics_prompt,
    log_analysis_prompt,
    nl_analytics_prompt,
    risk_explanation_prompt,
    strategy_explanation_prompt,
)
from algo_platform.modules.ai.infrastructure.null_provider import NullProvider


def test_assistant_prompt_without_context() -> None:
    prompt = assistant_prompt("What is my exposure?")
    assert "Algo Matrics trading assistant" in prompt.system
    assert "never invent numbers" in prompt.system
    assert prompt.user == "What is my exposure?"


def test_assistant_prompt_embeds_context() -> None:
    prompt = assistant_prompt("Explain", context={"equity": 1000})
    assert "equity" in prompt.user
    assert "Question: Explain" in prompt.user


def test_strategy_and_risk_prompts_include_context() -> None:
    s = strategy_explanation_prompt({"name": "SMA", "fast": 10})
    assert "SMA" in s.user and "Explain this strategy" in s.user
    r = risk_explanation_prompt({"max_daily_loss": 500})
    assert "max_daily_loss" in r.user


def test_log_analysis_truncates_and_joins() -> None:
    prompt = log_analysis_prompt([f"line {i}" for i in range(1000)])
    assert prompt.user.count("line ") == 400  # capped at 400 lines


def test_nl_analytics_and_broker_prompts() -> None:
    a = nl_analytics_prompt("How did I do?", {"sharpe": 1.2})
    assert "sharpe" in a.user and "How did I do?" in a.user
    b = broker_diagnostics_prompt({"broker": "zerodha", "healthy": False})
    assert "zerodha" in b.user


async def test_null_provider_is_deterministic_and_offline() -> None:
    provider = NullProvider()
    assert provider.name == "null"
    reply = await provider.complete(
        system="s", messages=[ChatMessage(role="user", content="Why did my order fail?")]
    )
    assert "not configured" in reply
    assert "Why did my order fail?" in reply


async def test_null_provider_handles_empty_history() -> None:
    reply = await NullProvider().complete(system="s", messages=[])
    assert "not configured" in reply


def test_factory_defaults_to_null(monkeypatch: pytest.MonkeyPatch) -> None:
    from algo_platform.config import Settings
    from algo_platform.modules.ai.infrastructure.factory import build_llm_provider

    settings = Settings(  # type: ignore[call-arg]
        database_url="postgresql+asyncpg://u:p@localhost/db",
        redis_url="redis://localhost:6379/0",
        jwt_private_key_pem="x",
        jwt_public_key_pem="x",
        broker_credential_kek_b64="x",
    )
    assert build_llm_provider(settings).name == "null"


def test_factory_anthropic_without_key_falls_back_to_null() -> None:
    from algo_platform.config import Settings
    from algo_platform.modules.ai.infrastructure.factory import build_llm_provider

    settings = Settings(  # type: ignore[call-arg]
        database_url="postgresql+asyncpg://u:p@localhost/db",
        redis_url="redis://localhost:6379/0",
        jwt_private_key_pem="x",
        jwt_public_key_pem="x",
        broker_credential_kek_b64="x",
        ai_provider="anthropic",
    )
    # No API key -> safe fallback, never constructs the Anthropic client.
    assert build_llm_provider(settings).name == "null"
