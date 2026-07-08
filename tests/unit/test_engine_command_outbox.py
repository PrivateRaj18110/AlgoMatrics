from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from algo_platform.shared.infrastructure.outbox import (
    OutboxEventModel,
    enqueue_engine_command,
)


async def test_engine_command_is_enqueued_in_database_transaction() -> None:
    session = MagicMock()
    organization_id = uuid4()
    order_id = uuid4()

    command_id = await enqueue_engine_command(
        session,
        command_type="submit_order",
        aggregate_type="order",
        aggregate_id=order_id,
        organization_id=organization_id,
        payload={"order_id": str(order_id), "mode": "paper"},
    )

    session.add.assert_called_once()
    row = session.add.call_args.args[0]
    assert isinstance(row, OutboxEventModel)
    assert row.event_id == command_id
    assert row.event_type == "engine.command.v1"
    assert row.aggregate_id == order_id
    assert row.organization_id == organization_id
    assert row.payload == {
        "type": "submit_order",
        "order_id": str(order_id),
        "mode": "paper",
    }
