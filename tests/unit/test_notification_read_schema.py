from sqlalchemy import UniqueConstraint

from algo_platform.modules.notifications.infrastructure.models import (
    NotificationReadModel,
)


def test_broadcast_notification_receipts_are_unique_per_user() -> None:
    table = NotificationReadModel.__table__
    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert ("notification_id", "user_id") in unique_columns
    assert table.c.notification_id.foreign_keys
    foreign_key = next(iter(table.c.notification_id.foreign_keys))
    assert foreign_key.target_fullname == "notifications.id"
    assert foreign_key.ondelete == "CASCADE"
