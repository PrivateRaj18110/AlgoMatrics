"""Unit tests for the AI assistant service (Phase 13, slice B)."""

from __future__ import annotations

from algo_platform.modules.ai.application.ports import ChatMessage
from algo_platform.modules.ai.application.service import PROMPT_TEMPLATES, AiAssistant


class _RecordingProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    @property
    def name(self) -> str:
        return "recording"

    async def complete(
        self, *, system: str, messages: list[ChatMessage], max_tokens: int = 2048
    ) -> str:
        self.calls.append((system, messages[0].content))
        return f"reply({max_tokens})"


async def test_ask_passes_prompt_and_max_tokens() -> None:
    provider = _RecordingProvider()
    assistant = AiAssistant(provider, max_tokens=512)
    answer = await assistant.ask(
        "Why did my order fail?", context={"order": {"status": "rejected"}}
    )
    assert answer == "reply(512)"
    system, user = provider.calls[0]
    assert "trading assistant" in system
    assert "order" in user and "Why did my order fail?" in user


async def test_each_capability_builds_a_distinct_prompt() -> None:
    provider = _RecordingProvider()
    assistant = AiAssistant(provider)
    await assistant.explain_strategy({"name": "SMA"})
    await assistant.explain_risk({"max_daily_loss": 100})
    await assistant.analyze_logs(["error: boom"])
    await assistant.analytics("How did I do?", {"sharpe": 1.1})
    await assistant.broker_diagnostics({"broker": "zerodha"})
    users = [user for _system, user in provider.calls]
    assert any("SMA" in u for u in users)
    assert any("max_daily_loss" in u for u in users)
    assert any("error: boom" in u for u in users)
    assert any("sharpe" in u for u in users)
    assert any("zerodha" in u for u in users)


def test_provider_name_exposed() -> None:
    assert AiAssistant(_RecordingProvider()).provider_name == "recording"


def test_prompt_templates_cover_capabilities() -> None:
    ids = {t["id"] for t in PROMPT_TEMPLATES}
    assert ids == {
        "assistant",
        "explain_strategy",
        "explain_risk",
        "analyze_logs",
        "analytics",
        "broker_diagnostics",
    }
