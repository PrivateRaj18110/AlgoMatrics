"""Optional: Claude reads material filings and refines their impact and direction.

Only used when the platform's AI provider is configured (``AI_PROVIDER=anthropic``
plus an API key). The model sees the filing's subject and NSE's one-line summary
— never a PDF — and answers in JSON; anything that does not parse is ignored
and the rule-based reading stands.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence

import structlog

from algo_platform.modules.ai.application.ports import ChatMessage, LLMProvider
from algo_platform.modules.market_insights.application.movers import FilingAssessment
from algo_platform.modules.market_insights.domain.catalysts import Catalyst

logger = structlog.get_logger(__name__)

_SYSTEM = (
    "You are an equity analyst covering Indian stocks in the NSE F&O segment. For each "
    "exchange filing you are given, judge how likely it is to move that stock's price "
    "materially during the next trading session. Reply with a JSON array only — one "
    'object per filing: {"id": <id>, "impact": <0..1>, "direction": <1|-1|0>, '
    '"note": <at most 20 words>}. impact 0 = routine paperwork, 0.5 = likely noticeable, '
    "1 = very likely a large move. direction 1 = likely up, -1 = likely down, 0 = unclear. "
    "Judge only from the text given; do not invent figures."
)
_BATCH = 20


class ClaudeFilingReader:
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    async def assess(self, filings: Sequence[Catalyst]) -> dict[str, FilingAssessment]:
        out: dict[str, FilingAssessment] = {}
        for start in range(0, len(filings), _BATCH):
            chunk = filings[start : start + _BATCH]
            prompt = json.dumps(
                [
                    {
                        "id": item.id,
                        "symbol": item.symbol,
                        "company": item.company,
                        "subject": item.label,
                        "text": item.title[:600],
                    }
                    for item in chunk
                ],
                ensure_ascii=False,
            )
            try:
                reply = await self._provider.complete(
                    system=_SYSTEM,
                    messages=[ChatMessage(role="user", content=prompt)],
                    max_tokens=2000,
                )
            except Exception:
                logger.warning("market_ai.read_failed", filings=len(chunk))
                continue
            out.update(parse_assessments(reply, {item.id for item in chunk}))
        return out


def parse_assessments(reply: str, allowed: set[str]) -> dict[str, FilingAssessment]:
    match = re.search(r"\[.*\]", reply, re.DOTALL)
    if not match:
        return {}
    try:
        items = json.loads(match.group(0))
    except ValueError:
        return {}
    out: dict[str, FilingAssessment] = {}
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or item.get("id") not in allowed:
            continue
        try:
            impact = max(0.0, min(1.0, float(item.get("impact") or 0.0)))
            direction = int(item.get("direction") or 0)
        except (TypeError, ValueError):
            continue
        out[str(item["id"])] = FilingAssessment(
            impact=impact,
            direction=max(-1, min(1, direction)),
            note=str(item.get("note") or "")[:160],
        )
    return out
