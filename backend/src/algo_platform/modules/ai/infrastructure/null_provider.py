"""Deterministic no-op LLM provider.

Used when no AI backend is configured (the default). It never makes a network
call, so the AI feature degrades gracefully and tests stay hermetic. It returns
a clear, deterministic message rather than a fabricated answer.
"""

from __future__ import annotations

from algo_platform.modules.ai.application.ports import ChatMessage


class NullProvider:
    @property
    def name(self) -> str:
        return "null"

    async def complete(
        self, *, system: str, messages: list[ChatMessage], max_tokens: int = 2048
    ) -> str:
        last = next((m.content for m in reversed(messages) if m.role == "user"), "")
        preview = last.strip().splitlines()[0][:200] if last.strip() else ""
        return (
            "AI is not configured on this platform. Set an AI provider to enable "
            "the assistant. "
            + (f'Your question was: "{preview}".' if preview else "")
        ).strip()
