"""Prompt templates for the AI platform (pure, framework-free).

Each builder returns a ``(system, user)`` pair assembled from caller-supplied
context. Keeping them pure makes the exact prompt text unit-testable and keeps
the provider layer free of copy. The system prompts constrain the assistant to
the trading domain and forbid fabricated numbers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

_BASE_SYSTEM = (
    "You are the Algo Matrics trading assistant. You help users understand their "
    "strategies, risk, orders, and platform diagnostics. Be concise and precise. "
    "Only use figures present in the provided context — never invent numbers, "
    "prices, or account values. If the context is insufficient, say so plainly. "
    "You do not place trades or change settings; you explain and advise."
)


@dataclass(frozen=True, slots=True)
class Prompt:
    system: str
    user: str


def _context_block(label: str, data: Any) -> str:
    return f"{label}:\n```json\n{json.dumps(data, indent=2, default=str)}\n```"


def assistant_prompt(question: str, *, context: dict[str, Any] | None = None) -> Prompt:
    user = question.strip()
    if context:
        user = f"{_context_block('Context', context)}\n\nQuestion: {user}"
    return Prompt(system=_BASE_SYSTEM, user=user)


def strategy_explanation_prompt(strategy: dict[str, Any]) -> Prompt:
    system = (
        _BASE_SYSTEM + " Explain the strategy's logic, parameters, and when it "
        "enters or exits, in plain language a trader can act on."
    )
    user = _context_block("Strategy", strategy) + "\n\nExplain this strategy."
    return Prompt(system=system, user=user)


def risk_explanation_prompt(risk: dict[str, Any]) -> Prompt:
    system = (
        _BASE_SYSTEM + " Explain the risk configuration and what each limit "
        "protects against, and flag anything unusual."
    )
    user = _context_block("Risk configuration", risk) + "\n\nExplain this risk setup."
    return Prompt(system=system, user=user)


def log_analysis_prompt(log_lines: list[str]) -> Prompt:
    system = (
        _BASE_SYSTEM + " Analyze the log excerpt: identify errors, likely causes, "
        "and concrete next steps. Group related lines."
    )
    joined = "\n".join(line.strip() for line in log_lines[:400])
    user = f"Logs:\n```\n{joined}\n```\n\nWhat is going on and what should I check?"
    return Prompt(system=system, user=user)


def nl_analytics_prompt(question: str, metrics: dict[str, Any]) -> Prompt:
    system = (
        _BASE_SYSTEM + " Answer the analytics question strictly from the metrics "
        "provided. Show the relevant figures you used."
    )
    user = _context_block("Metrics", metrics) + f"\n\nQuestion: {question.strip()}"
    return Prompt(system=system, user=user)


def broker_diagnostics_prompt(diagnostics: dict[str, Any]) -> Prompt:
    system = (
        _BASE_SYSTEM + " Diagnose the broker connection from the status data: "
        "state the likely problem and the remediation steps in order."
    )
    user = _context_block("Broker status", diagnostics) + "\n\nDiagnose this connection."
    return Prompt(system=system, user=user)
