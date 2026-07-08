"""Transactional e-mail outbox and retryable delivery queries."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import BigInteger, DateTime, Index, String, Text, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from algo_platform.shared.application.ports import EmailMessage
from algo_platform.shared.domain.types import utc_now
from algo_platform.shared.infrastructure.database import Base


class EmailOutboxModel(Base):
    __tablename__ = "email_outbox"
    __table_args__ = (
        Index(
            "ix_email_outbox_pending",
            "available_at",
            postgresql_where=text("sent_at IS NULL AND attempts < 10"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    recipient: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(300))
    text_body: Mapped[str] = mapped_column(Text)
    html_body: Mapped[str | None] = mapped_column(Text, default=None)
    attempts: Mapped[int] = mapped_column(BigInteger, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_error: Mapped[str | None] = mapped_column(String(1000), default=None)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    def message(self) -> EmailMessage:
        return EmailMessage(
            to=self.recipient,
            subject=self.subject,
            text=self.text_body,
            html=self.html_body,
        )


class TransactionalEmailSender:
    """Implements the application port by writing inside the request transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def send(self, message: EmailMessage) -> None:
        self._session.add(
            EmailOutboxModel(
                recipient=message.to.strip().lower(),
                subject=message.subject,
                text_body=message.text,
                html_body=message.html,
            )
        )


async def fetch_pending_emails(
    session: AsyncSession, *, limit: int = 20
) -> list[EmailOutboxModel]:
    result = await session.execute(
        select(EmailOutboxModel)
        .where(
            EmailOutboxModel.sent_at.is_(None),
            EmailOutboxModel.attempts < 10,
            EmailOutboxModel.available_at <= utc_now(),
        )
        .order_by(EmailOutboxModel.available_at, EmailOutboxModel.created_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list(result.scalars().all())


def mark_email_sent(row: EmailOutboxModel) -> None:
    row.attempts += 1
    row.sent_at = utc_now()
    row.last_error = None


def mark_email_failed(row: EmailOutboxModel, error: Exception) -> None:
    row.attempts += 1
    delay_seconds = min(3600, 2 ** min(row.attempts, 10) * 15)
    row.available_at = utc_now() + timedelta(seconds=delay_seconds)
    row.last_error = str(error)[:1000]
