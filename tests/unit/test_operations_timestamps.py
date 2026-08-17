from datetime import UTC, datetime

from algo_platform.modules.operations.application.timestamps import to_utc_z


def test_naive_datetime_is_treated_as_utc_z() -> None:
    stamp = datetime(2026, 8, 17, 12, 0, 0)
    assert to_utc_z(stamp) == "2026-08-17T12:00:00Z"


def test_offset_datetime_converts_to_utc() -> None:
    assert to_utc_z(datetime(2026, 8, 17, 12, 0, tzinfo=UTC)).endswith("Z")
    assert to_utc_z(None) is None
