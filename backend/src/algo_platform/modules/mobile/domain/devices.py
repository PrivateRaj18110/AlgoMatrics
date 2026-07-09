"""Mobile device domain: platforms, push-token validation, notification shape.

Pure and framework-free so the rules are unit testable and reusable by the
device registry, push channel, and any tooling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from algo_platform.shared.domain.errors import ValidationFailed


class DevicePlatform(StrEnum):
    IOS = "ios"
    ANDROID = "android"
    WEB = "web"


# Bounds keep obviously-bogus tokens out of the store; the push provider is the
# authority on real validity. FCM/APNs tokens are well under this length.
_MIN_TOKEN_LEN = 16
_MAX_TOKEN_LEN = 4096


def normalize_push_token(raw: str) -> str:
    """Trim and validate a push token; raise on empty/short/oversized input."""

    token = raw.strip()
    if not token:
        raise ValidationFailed("push token must not be empty")
    if len(token) < _MIN_TOKEN_LEN:
        raise ValidationFailed("push token is too short")
    if len(token) > _MAX_TOKEN_LEN:
        raise ValidationFailed("push token is too long")
    if any(c.isspace() for c in token):
        raise ValidationFailed("push token must not contain whitespace")
    return token


def parse_platform(value: str) -> DevicePlatform:
    try:
        return DevicePlatform(value.strip().lower())
    except ValueError as exc:
        raise ValidationFailed(f"unsupported device platform: {value!r}") from exc


@dataclass(frozen=True, slots=True)
class PushMessage:
    """A provider-agnostic push payload."""

    title: str
    body: str
    data: dict[str, Any] = field(default_factory=dict)
    badge: int | None = None

    def truncated(self, *, title_max: int = 178, body_max: int = 2000) -> PushMessage:
        """A copy clamped to conservative APNs/FCM display limits."""

        return PushMessage(
            title=self.title[:title_max],
            body=self.body[:body_max],
            data=self.data,
            badge=self.badge,
        )
