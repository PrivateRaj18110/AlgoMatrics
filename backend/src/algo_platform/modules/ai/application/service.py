"""AI assistant service: turn platform context into prompts and call the model."""

from __future__ import annotations

from typing import Any

from algo_platform.modules.ai.application.ports import ChatMessage, LLMProvider
from algo_platform.modules.ai.domain import prompts


class AiAssistant:
    def __init__(self, provider: LLMProvider, *, max_tokens: int = 2048) -> None:
        self._provider = provider
        self._max_tokens = max_tokens

    @property
    def provider_name(self) -> str:
        return self._provider.name

    async def _run(self, prompt: prompts.Prompt) -> str:
        return await self._provider.complete(
            system=prompt.system,
            messages=[ChatMessage(role="user", content=prompt.user)],
            max_tokens=self._max_tokens,
        )

    async def ask(self, question: str, *, context: dict[str, Any] | None = None) -> str:
        return await self._run(prompts.assistant_prompt(question, context=context))

    async def explain_strategy(self, strategy: dict[str, Any]) -> str:
        return await self._run(prompts.strategy_explanation_prompt(strategy))

    async def explain_risk(self, risk: dict[str, Any]) -> str:
        return await self._run(prompts.risk_explanation_prompt(risk))

    async def analyze_logs(self, lines: list[str]) -> str:
        return await self._run(prompts.log_analysis_prompt(lines))

    async def analytics(self, question: str, metrics: dict[str, Any]) -> str:
        return await self._run(prompts.nl_analytics_prompt(question, metrics))

    async def broker_diagnostics(self, status: dict[str, Any]) -> str:
        return await self._run(prompts.broker_diagnostics_prompt(status))


def _t(id_: str, label: str, description: str) -> dict[str, str]:
    return {"id": id_, "label": label, "description": description}


PROMPT_TEMPLATES = [
    _t("assistant", "Trading assistant", "Ask anything about the platform"),
    _t("explain_strategy", "Explain a strategy", "Plain-language strategy walkthrough"),
    _t("explain_risk", "Explain risk", "What your risk limits protect against"),
    _t("analyze_logs", "Analyze logs", "Find errors and next steps in logs"),
    _t("analytics", "NL analytics", "Ask about your metrics in plain English"),
    _t("broker_diagnostics", "Broker diagnostics", "Diagnose a broker connection"),
]
