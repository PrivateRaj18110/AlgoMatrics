"""External notification delivery channels: email and outbound webhook.

Each channel is a thin adapter behind the :class:`NotificationDispatcher`
facade the service uses. In-app delivery is handled directly by the service
(DB write + Redis publish); this module covers the opt-in external surfaces.

The webhook target URL is operator-supplied, so it is validated against an
SSRF guard (HTTPS only, no loopback/private/reserved hosts) before any request.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx
import structlog

from algo_platform.shared.application.circuit_breaker import CircuitBreaker
from algo_platform.shared.application.ports import EmailMessage, EmailSender
from algo_platform.shared.domain.errors import ValidationFailed

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class OutboundNotification:
    """The payload handed to external channels."""

    type: str
    severity: str
    title: str
    body: str
    payload: dict[str, Any]


class NotificationChannelSender(Protocol):
    async def send(self, notification: OutboundNotification, *, target: str) -> None: ...


def validate_webhook_url(url: str) -> str:
    """Reject non-HTTPS and internal targets (SSRF guard) for webhook URLs."""

    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise ValidationFailed("webhook URL must be an https URL")
    host = parts.hostname.lower()
    if host in {"localhost", "localhost.localdomain"}:
        raise ValidationFailed("webhook URL host is not allowed")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # A DNS name; further resolution is enforced at request time by the
        # runtime's egress policy. Literal private IPs are the common SSRF path.
        return url
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
        raise ValidationFailed("webhook URL host is not allowed")
    return url


class EmailNotificationChannel:
    """Delivers a notification as a transactional email."""

    def __init__(self, sender: EmailSender) -> None:
        self._sender = sender

    async def send(self, notification: OutboundNotification, *, target: str) -> None:
        subject = f"[{notification.severity.upper()}] {notification.title}"
        await self._sender.send(
            EmailMessage(to=target, subject=subject, text=notification.body or notification.title)
        )


class WebhookNotificationChannel:
    """POSTs a JSON notification to an operator-configured HTTPS endpoint.

    An optional circuit breaker stops repeated calls to a failing endpoint from
    piling up; while it is open the send is rejected fast (surfaced as a channel
    failure the dispatcher swallows).
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        timeout_seconds: float = 5.0,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self._client = client
        self._timeout = timeout_seconds
        self._breaker = breaker

    async def send(self, notification: OutboundNotification, *, target: str) -> None:
        url = validate_webhook_url(target)

        async def _post() -> None:
            await self._client.post(
                url,
                json={
                    "type": notification.type,
                    "severity": notification.severity,
                    "title": notification.title,
                    "body": notification.body,
                    "payload": notification.payload,
                },
                timeout=self._timeout,
            )

        if self._breaker is not None:
            await self._breaker.call(_post)
        else:
            await _post()


class NotificationDispatcher:
    """Fans an external notification out to the requested channels.

    Failures on any one channel are logged, not raised: a webhook outage must
    never break the in-app notification (which is already persisted) or the
    business transaction that triggered it.
    """

    def __init__(
        self,
        *,
        email: NotificationChannelSender | None = None,
        webhook: NotificationChannelSender | None = None,
    ) -> None:
        self._email = email
        self._webhook = webhook

    async def send_email(self, notification: OutboundNotification, *, to: str) -> None:
        if self._email is None:
            return
        await self._guarded(self._email, notification, target=to, channel="email")

    async def send_webhook(self, notification: OutboundNotification, *, url: str) -> None:
        if self._webhook is None:
            return
        await self._guarded(self._webhook, notification, target=url, channel="webhook")

    async def _guarded(
        self,
        sender: NotificationChannelSender,
        notification: OutboundNotification,
        *,
        target: str,
        channel: str,
    ) -> None:
        try:
            await sender.send(notification, target=target)
        except Exception as exc:  # channel failures must not propagate
            logger.warning(
                "notification.channel_delivery_failed",
                channel=channel,
                type=notification.type,
                error=str(exc),
            )


def build_dispatcher(
    email_sender: EmailSender,
    http_client: httpx.AsyncClient,
    *,
    webhook_breaker: CircuitBreaker | None = None,
) -> NotificationDispatcher:
    """Assemble a dispatcher from the app's shared email + HTTP clients."""

    return NotificationDispatcher(
        email=EmailNotificationChannel(email_sender),
        webhook=WebhookNotificationChannel(http_client, breaker=webhook_breaker),
    )
