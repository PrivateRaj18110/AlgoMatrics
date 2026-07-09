"""Construct the configured LLM provider."""

from __future__ import annotations

from algo_platform.config import Settings
from algo_platform.modules.ai.application.ports import LLMProvider
from algo_platform.modules.ai.infrastructure.null_provider import NullProvider


def build_llm_provider(settings: Settings) -> LLMProvider:
    if settings.ai_provider == "anthropic" and settings.anthropic_api_key:
        from algo_platform.modules.ai.infrastructure.anthropic_provider import AnthropicProvider

        return AnthropicProvider(api_key=settings.anthropic_api_key, model=settings.ai_model)
    # Default / unconfigured: never calls out.
    return NullProvider()
