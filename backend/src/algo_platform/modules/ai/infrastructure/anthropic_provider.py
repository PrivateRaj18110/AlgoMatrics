"""Anthropic Claude provider (official SDK, adaptive thinking).

Uses the async Anthropic SDK. The client is created lazily so the optional
``anthropic`` dependency is only needed when this provider is selected.
"""

from __future__ import annotations

import structlog

from algo_platform.modules.ai.application.ports import ChatMessage

logger = structlog.get_logger("ai")

# Default to the most capable current model; adaptive thinking lets Claude decide
# how much to reason per request.
_DEFAULT_MODEL = "claude-opus-4-8"


class AnthropicProvider:
    def __init__(self, *, api_key: str, model: str = _DEFAULT_MODEL) -> None:
        if not api_key:
            raise ValueError("Anthropic provider requires an API key")
        self._api_key = api_key
        self._model = model
        self._client: object | None = None

    @property
    def name(self) -> str:
        return "anthropic"

    def _get_client(self) -> object:
        if self._client is None:
            from anthropic import AsyncAnthropic  # lazy: optional dependency

            self._client = AsyncAnthropic(api_key=self._api_key)
        return self._client

    async def complete(
        self, *, system: str, messages: list[ChatMessage], max_tokens: int = 2048
    ) -> str:
        client = self._get_client()
        response = await client.messages.create(  # type: ignore[attr-defined]
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            thinking={"type": "adaptive"},
            messages=[{"role": m.role, "content": m.content} for m in messages],
        )
        # Extract text blocks; adaptive thinking also returns (empty) thinking blocks.
        parts = [block.text for block in response.content if block.type == "text"]
        return "".join(parts).strip()
