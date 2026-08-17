from datetime import UTC, datetime, timedelta

from algo_platform.modules.operations.application.machine_status import (
    DEGRADED_AFTER_SEC,
    OFFLINE_AFTER_SEC,
    derive_machine_status,
)


def test_heartbeat_age_matches_ops_timeouts() -> None:
    now = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
    assert derive_machine_status("online", now, now=now) == "online"
    assert (
        derive_machine_status("online", now - timedelta(seconds=DEGRADED_AFTER_SEC + 1), now=now)
        == "degraded"
    )
    assert (
        derive_machine_status("online", now - timedelta(seconds=OFFLINE_AFTER_SEC + 1), now=now)
        == "offline"
    )
    assert derive_machine_status("online", None, now=now) == "unknown"
