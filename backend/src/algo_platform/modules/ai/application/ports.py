"""LLM provider port. Concrete providers (Anthropic, null) plug in behind this."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Literal["user", "assistant"]
    content: str


class LLMProvider(Protocol):
    """Command-side interface for a chat-completion model."""

    @property
    def name(self) -> str: ...

    async def complete(
        self,
        *,
        system: str,
        messages: list[ChatMessage],
        max_tokens: int = 2048,
    ) -> str:
        """Return the assistant's text reply for the given system prompt + turns."""
        ...
