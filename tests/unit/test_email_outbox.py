from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock

from algo_platform.shared.application.ports import EmailMessage
from algo_platform.shared.domain.types import utc_now
from algo_platform.shared.infrastructure.email_outbox import (
    EmailOutboxModel,
    TransactionalEmailSender,
    mark_email_failed,
    mark_email_sent,
)


async def test_transactional_sender_enqueues_without_delivering() -> None:
    session = MagicMock()
    sender = TransactionalEmailSender(session)

    await sender.send(
        EmailMessage(
            to=" Trader@Example.com ",
            subject="Verify",
            text="verification body",
        )
    )

    session.add.assert_called_once()
    row = session.add.call_args.args[0]
    assert isinstance(row, EmailOutboxModel)
    assert row.recipient == "trader@example.com"
    assert row.subject == "Verify"
    assert row.sent_at is None


def test_email_delivery_state_uses_bounded_retry_backoff() -> None:
    row = EmailOutboxModel(
        recipient="trader@example.com",
        subject="Reset",
        text_body="body",
        attempts=0,
        available_at=utc_now(),
    )
    before = utc_now()

    mark_email_failed(row, RuntimeError("SMTP unavailable"))

    assert row.attempts == 1
    assert row.last_error == "SMTP unavailable"
    assert row.available_at >= before + timedelta(seconds=29)
    assert row.sent_at is None

    mark_email_sent(row)
    assert row.attempts == 2
    assert row.sent_at is not None
    assert row.last_error is None
