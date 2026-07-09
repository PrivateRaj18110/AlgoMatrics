"""Unit tests for pure mobile device domain + null push provider (Phase 16)."""

from __future__ import annotations

import pytest

from algo_platform.modules.mobile.application.ports import PushTarget
from algo_platform.modules.mobile.domain.devices import (
    DevicePlatform,
    PushMessage,
    normalize_push_token,
    parse_platform,
)
from algo_platform.modules.mobile.infrastructure.null_provider import NullPushProvider
from algo_platform.shared.domain.errors import ValidationFailed

VALID_TOKEN = "a" * 40


def test_normalize_push_token_trims_and_returns() -> None:
    assert normalize_push_token(f"  {VALID_TOKEN}  ") == VALID_TOKEN


@pytest.mark.parametrize("bad", ["", "   ", "short", "a" * 5000, "has space " + VALID_TOKEN])
def test_normalize_push_token_rejects_bad_input(bad: str) -> None:
    with pytest.raises(ValidationFailed):
        normalize_push_token(bad)


def test_parse_platform_accepts_known_and_normalizes_case() -> None:
    assert parse_platform("iOS") is DevicePlatform.IOS
    assert parse_platform(" android ") is DevicePlatform.ANDROID
    assert parse_platform("web") is DevicePlatform.WEB


def test_parse_platform_rejects_unknown() -> None:
    with pytest.raises(ValidationFailed):
        parse_platform("blackberry")


def test_push_message_truncates_to_limits() -> None:
    msg = PushMessage(title="T" * 300, body="B" * 5000, data={"k": "v"}, badge=3)
    clamped = msg.truncated()
    assert len(clamped.title) == 178
    assert len(clamped.body) == 2000
    assert clamped.data == {"k": "v"}
    assert clamped.badge == 3


async def test_null_provider_reports_all_delivered() -> None:
    provider = NullPushProvider()
    targets = [
        PushTarget(token=VALID_TOKEN, platform=DevicePlatform.IOS),
        PushTarget(token="b" * 40, platform=DevicePlatform.ANDROID),
    ]
    result = await provider.send(PushMessage(title="hi", body="there"), targets)
    assert result.delivered == 2
    assert result.invalid_tokens == ()
