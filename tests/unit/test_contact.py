"""Public contact form."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from algo_platform.modules.contact.application import service as contact_module
from algo_platform.modules.contact.application.service import ContactService
from algo_platform.modules.contact.infrastructure.models import ContactMessageModel
from algo_platform.modules.contact.presentation.router import ContactRequest, contact
from algo_platform.shared.application.ports import EmailMessage
from algo_platform.shared.domain.errors import ConflictError, NotFoundError
from algo_platform.shared.domain.types import utc_now
from algo_platform.shared.infrastructure.client_context import ClientInfo, set_client


class FakeSession:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.rows: dict[Any, Any] = {}

    def add(self, model: Any) -> None:
        self.added.append(model)
        if getattr(model, "id", None) is None:
            model.id = uuid4()
        self.rows[model.id] = model

    async def flush(self) -> None:
        return None

    async def get(self, _model: Any, key: Any) -> Any:
        return self.rows.get(key)


class Outbox:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.sent.append(message)


class FakeDirectory:
    def __init__(self, _session: Any) -> None:
        pass

    async def platform_admin_emails(self) -> list[str]:
        return ["owner@example.com"]


def _service(session: FakeSession, outbox: Outbox) -> ContactService:
    return ContactService(session=session, email_sender=outbox, app_base_url="https://x.test")  # type: ignore[arg-type]


async def test_honeypot_submissions_are_dropped_silently() -> None:
    class Exploding:
        async def submit(self, **_: Any) -> None:
            raise AssertionError("a bot submission must never be stored")

    payload = ContactRequest(
        name="Bot", email="bot@example.com", message="buy cheap followers now", website="http://x"
    )
    response = await contact(payload, Exploding())  # type: ignore[arg-type]
    assert "received" in response.message


async def test_message_is_stored_with_client_and_admins_are_told(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(contact_module, "UserDirectory", FakeDirectory)
    set_client(ClientInfo(ip_address="192.168.1.9", user_agent="Firefox"))
    session, outbox = FakeSession(), Outbox()
    try:
        await _service(session, outbox).submit(
            name=" Asha ", email="Asha@Example.com", topic="partnership", message=" Hello team "
        )
    finally:
        set_client(None)

    (stored,) = session.added
    assert (stored.name, stored.email, stored.message) == ("Asha", "asha@example.com", "Hello team")
    assert stored.ip_address == "192.168.1.9"
    assert stored.geo["country"] == "Private network"
    (mail,) = outbox.sent
    assert mail.to == "owner@example.com"
    assert "asha@example.com" in mail.text and "/app/admin/messages" in mail.text


async def test_unknown_topic_falls_back_to_other(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(contact_module, "UserDirectory", FakeDirectory)
    session = FakeSession()
    await _service(session, Outbox()).submit(
        name="A", email="a@example.com", topic="nonsense", message="0123456789"
    )
    assert session.added[0].topic == "other"


async def test_resolve_once() -> None:
    session = FakeSession()
    model = ContactMessageModel(
        id=uuid4(),
        name="A",
        email="a@example.com",
        topic="other",
        message="hi there team",
        status="open",
        created_at=utc_now(),
    )
    session.rows[model.id] = model
    service = _service(session, Outbox())

    resolved = await service.resolve(model.id, resolved_by=uuid4())
    assert resolved.status == "resolved" and resolved.resolved_at is not None
    with pytest.raises(ConflictError):
        await service.resolve(model.id, resolved_by=uuid4())
    with pytest.raises(NotFoundError):
        await service.resolve(uuid4(), resolved_by=uuid4())
