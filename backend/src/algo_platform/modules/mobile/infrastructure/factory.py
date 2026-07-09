"""Construct the configured push provider."""

from __future__ import annotations

from algo_platform.config import Settings
from algo_platform.modules.mobile.application.ports import PushProvider
from algo_platform.modules.mobile.infrastructure.null_provider import NullPushProvider


def build_push_provider(settings: Settings) -> PushProvider:
    # "fcm" is recognised for forward compatibility; until credentials and the
    # FCM adapter are provisioned it falls back to the safe, offline provider.
    return NullPushProvider()
