"""AI platform HTTP API. Gated by the ``ai`` feature flag."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from algo_platform.api.dependencies.core import SettingsDep
from algo_platform.api.dependencies.tenant import TenantDep
from algo_platform.modules.ai.application.service import PROMPT_TEMPLATES, AiAssistant
from algo_platform.modules.ai.infrastructure.factory import build_llm_provider
from algo_platform.modules.feature_flags.presentation.dependencies import require_feature

router = APIRouter(
    prefix="/ai",
    tags=["ai"],
    dependencies=[Depends(require_feature("ai"))],
)


def get_assistant(request: Request, settings: SettingsDep) -> AiAssistant:
    provider = getattr(request.app.state, "llm", None) or build_llm_provider(settings)
    return AiAssistant(provider, max_tokens=settings.ai_max_tokens)


AssistantDep = Annotated[AiAssistant, Depends(get_assistant)]


class AnswerResponse(BaseModel):
    answer: str
    provider: str


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    context: dict[str, Any] | None = None


class ContextRequest(BaseModel):
    context: dict[str, Any]


class LogsRequest(BaseModel):
    lines: list[str] = Field(min_length=1, max_length=1000)


class AnalyticsRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    metrics: dict[str, Any]


def _answer(assistant: AiAssistant, text: str) -> AnswerResponse:
    return AnswerResponse(answer=text, provider=assistant.provider_name)


@router.get("/prompt-templates", response_model=list[dict[str, str]])
async def prompt_templates(tenant: TenantDep) -> list[dict[str, str]]:
    return PROMPT_TEMPLATES


@router.post("/assistant", response_model=AnswerResponse)
async def assistant(
    payload: AskRequest, tenant: TenantDep, assistant_svc: AssistantDep
) -> AnswerResponse:
    text = await assistant_svc.ask(payload.question, context=payload.context)
    return _answer(assistant_svc, text)


@router.post("/explain-strategy", response_model=AnswerResponse)
async def explain_strategy(
    payload: ContextRequest, tenant: TenantDep, assistant_svc: AssistantDep
) -> AnswerResponse:
    return _answer(assistant_svc, await assistant_svc.explain_strategy(payload.context))


@router.post("/explain-risk", response_model=AnswerResponse)
async def explain_risk(
    payload: ContextRequest, tenant: TenantDep, assistant_svc: AssistantDep
) -> AnswerResponse:
    return _answer(assistant_svc, await assistant_svc.explain_risk(payload.context))


@router.post("/analyze-logs", response_model=AnswerResponse)
async def analyze_logs(
    payload: LogsRequest, tenant: TenantDep, assistant_svc: AssistantDep
) -> AnswerResponse:
    return _answer(assistant_svc, await assistant_svc.analyze_logs(payload.lines))


@router.post("/analytics", response_model=AnswerResponse)
async def analytics(
    payload: AnalyticsRequest, tenant: TenantDep, assistant_svc: AssistantDep
) -> AnswerResponse:
    text = await assistant_svc.analytics(payload.question, payload.metrics)
    return _answer(assistant_svc, text)


@router.post("/broker-diagnostics", response_model=AnswerResponse)
async def broker_diagnostics(
    payload: ContextRequest, tenant: TenantDep, assistant_svc: AssistantDep
) -> AnswerResponse:
    return _answer(assistant_svc, await assistant_svc.broker_diagnostics(payload.context))
