"""E-mail delivery adapters.

``SmtpEmailSender`` performs real SMTP delivery (STARTTLS or implicit TLS).
``ConsoleEmailSender`` is the development backend: it writes the full message
to the structured log so verification/reset links are usable locally without
an SMTP relay, mirroring framework console backends. Selection is explicit
via ``EMAIL_BACKEND``.
"""

from __future__ import annotations

import asyncio
import smtplib
import ssl
from email.message import EmailMessage as MimeMessage

import structlog

from algo_platform.config import Settings
from algo_platform.shared.application.ports import EmailMessage, EmailSender

logger = structlog.get_logger(__name__)


class ConsoleEmailSender:
    async def send(self, message: EmailMessage) -> None:
        logger.info(
            "email.console_delivery",
            to=message.to,
            subject=message.subject,
            body=message.text,
        )


class SmtpEmailSender:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        starttls: bool,
        sender: str,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._starttls = starttls
        self._sender = sender

    async def send(self, message: EmailMessage) -> None:
        await asyncio.to_thread(self._send_sync, message)

    def _send_sync(self, message: EmailMessage) -> None:
        mime = MimeMessage()
        mime["From"] = self._sender
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.text)
        if message.html:
            mime.add_alternative(message.html, subtype="html")

        context = ssl.create_default_context()
        if self._starttls:
            with smtplib.SMTP(self._host, self._port, timeout=30) as client:
                client.starttls(context=context)
                if self._username and self._password:
                    client.login(self._username, self._password)
                client.send_message(mime)
        else:
            with smtplib.SMTP_SSL(self._host, self._port, timeout=30, context=context) as client:
                if self._username and self._password:
                    client.login(self._username, self._password)
                client.send_message(mime)


def create_email_sender(settings: Settings) -> EmailSender:
    if settings.email_backend == "smtp":
        if not settings.smtp_host:
            raise RuntimeError("EMAIL_BACKEND=smtp requires SMTP_HOST")
        return SmtpEmailSender(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            starttls=settings.smtp_starttls,
            sender=settings.email_from,
        )
    return ConsoleEmailSender()
