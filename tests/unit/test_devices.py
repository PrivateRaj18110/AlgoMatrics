"""Device ingest: event validation, heartbeat/positions handling, keys, status."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from algo_platform.modules.devices.application.service import (
    MAX_NOTIFICATIONS_PER_REQUEST,
    DeviceService,
    device_status,
)
from algo_platform.modules.devices.domain.events import MAX_EVENTS_PER_REQUEST, parse_events
from algo_platform.modules.devices.infrastructure.models import DeviceEventModel, DeviceModel
from algo_platform.shared.domain.errors import AuthenticationFailed
from algo_platform.shared.domain.types import utc_now

NOW = datetime(2026, 9, 19, 4, 0, tzinfo=UTC)


# -- parsing -----------------------------------------------------------------------------


def test_accepts_single_event_list_or_envelope() -> None:
    heartbeat = {"type": "heartbeat", "cpu": 12}
    for body in (heartbeat, [heartbeat], {"events": [heartbeat]}):
        result = parse_events(body, now=NOW)
        assert len(result.accepted) == 1 and result.rejected == []


def test_heartbeat_metrics_are_validated_and_kept() -> None:
    (event,) = parse_events(
        {
            "type": "heartbeat",
            "cpu": 41.234,
            "ram": "63",
            "disk": 70,
            "latency_ms": 18,
            "version": "1.4.2",
            "metrics": {"open_orders": 3},
        },
        now=NOW,
    ).accepted
    assert event.payload == {
        "cpu": 41.23,
        "ram": 63.0,
        "disk": 70.0,
        "latency_ms": 18.0,
        "open_orders": 3.0,
        "version": "1.4.2",
    }
    assert event.occurred_at == NOW  # no ts -> received time


@pytest.mark.parametrize(
    ("event", "reason"),
    [
        ({"type": "heartbeat", "cpu": 140}, "cpu must be between"),
        ({"type": "heartbeat", "cpu": True}, "cpu must be a number"),
        (
            {"type": "trade", "symbol": "SBIN", "side": "hold", "qty": 1, "price": 1},
            "side must be buy or sell",
        ),
        ({"type": "trade", "side": "buy", "qty": 1, "price": 1}, "symbol is required"),
        ({"type": "log", "level": "loud", "message": "x"}, "level must be one of"),
        ({"type": "alert", "severity": "warning"}, "message is required"),
        ({"type": "positions", "positions": "SBIN"}, "positions must be a list"),
        ({"type": "teleport"}, "type must be one of"),
        ({"type": "log", "message": "x", "ts": "yesterday"}, "ts must be ISO-8601"),
        ("not an object", "each event must be a JSON object"),
    ],
)
def test_invalid_events_are_rejected_with_a_reason(event: Any, reason: str) -> None:
    result = parse_events([event], now=NOW)
    assert result.accepted == []
    assert reason in result.rejected[0]["reason"]


def test_one_bad_event_does_not_lose_the_batch() -> None:
    result = parse_events(
        [
            {"type": "log", "message": "ok"},
            {"type": "nope"},
            {"type": "alert", "message": "disk full"},
        ],
        now=NOW,
    )
    assert [e.kind for e in result.accepted] == ["log", "alert"]
    assert [r["index"] for r in result.rejected] == [1]


def test_trade_is_normalised_with_a_readable_message() -> None:
    (event,) = parse_events(
        {
            "type": "trade",
            "symbol": "reliance",
            "side": "BUY",
            "qty": "10",
            "price": 2901.5,
            "pnl": -120,
            "strategy": "H30-X2",
            "ts": 1789790400,
        },
        now=NOW,
    ).accepted
    assert event.message == "BUY 10 RELIANCE @ 2901.5"
    assert event.payload["pnl"] == -120.0 and event.payload["strategy"] == "H30-X2"
    assert event.occurred_at == datetime.fromtimestamp(1789790400, tz=UTC)


def test_millisecond_and_iso_timestamps() -> None:
    ms, iso = parse_events(
        [
            {"type": "log", "message": "a", "ts": 1789790400000},
            {"type": "log", "message": "b", "ts": "2026-09-19T09:30:00+05:30"},
        ],
        now=NOW,
    ).accepted
    assert ms.occurred_at == datetime.fromtimestamp(1789790400, tz=UTC)
    assert iso.occurred_at == datetime(2026, 9, 19, 4, 0, tzinfo=UTC)


def test_batch_size_is_capped() -> None:
    result = parse_events([{"type": "log", "message": "x"}] * (MAX_EVENTS_PER_REQUEST + 1), now=NOW)
    assert result.accepted == [] and "at most" in result.rejected[0]["reason"]


def test_only_alerts_and_errors_are_notable() -> None:
    events = parse_events(
        [
            {"type": "log", "level": "info", "message": "started"},
            {"type": "log", "level": "error", "message": "broker timeout"},
            {"type": "alert", "severity": "warning", "message": "drawdown 3%"},
            {"type": "alert", "severity": "info", "message": "fyi"},
        ],
        now=NOW,
    ).accepted
    assert [e.is_notable for e in events] == [False, True, True, False]


# -- service ------------------------------------------------------------------------------


class FakeSession:
    def __init__(self, *rows: Any) -> None:
        self.added: list[Any] = []
        self.rows = list(rows)

    def add(self, model: Any) -> None:
        self.added.append(model)

    async def flush(self) -> None:
        return None


class FakeNotifications:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def notify(self, **kwargs: Any) -> None:
        self.sent.append(kwargs)


def _device() -> DeviceModel:
    return DeviceModel(
        id=uuid4(),
        organization_id=uuid4(),
        name="VPS-Mumbai-1",
        kind="vps",
        key_prefix="abcd1234",
        key_hash="x",
        created_at=NOW,
    )


async def test_ingest_updates_heartbeat_in_place_and_stores_the_rest() -> None:
    device, session, notes = _device(), FakeSession(), FakeNotifications()
    events = parse_events(
        [
            {"type": "heartbeat", "cpu": 20, "ts": "2026-09-19T03:59:00Z"},
            {"type": "heartbeat", "cpu": 35, "ts": "2026-09-19T03:58:00Z"},  # older: ignored
            {"type": "trade", "symbol": "SBIN", "side": "sell", "qty": 5, "price": 842},
            {"type": "positions", "positions": [{"symbol": "SBIN", "qty": -5, "avg_price": 842}]},
            {"type": "alert", "severity": "critical", "message": "kill switch tripped"},
        ],
        now=NOW,
    ).accepted
    counts = await DeviceService(session, notes).ingest(device, events, ip="203.0.113.7")  # type: ignore[arg-type]

    assert counts == {"heartbeat": 2, "trade": 1, "positions": 1, "alert": 1}
    assert device.health == {"cpu": 20.0} and device.last_ip == "203.0.113.7"
    assert device.positions == [{"symbol": "SBIN", "qty": -5.0, "avg_price": 842.0}]
    stored = [m for m in session.added if isinstance(m, DeviceEventModel)]
    assert sorted(m.kind for m in stored) == ["alert", "positions", "trade"]  # no heartbeat rows
    (note,) = notes.sent
    assert note["severity"] == "critical" and "kill switch tripped" in note["title"]


async def test_notifications_are_capped_per_request() -> None:
    notes = FakeNotifications()
    flood = parse_events(
        [{"type": "alert", "severity": "critical", "message": f"#{i}"} for i in range(20)], now=NOW
    )
    await DeviceService(FakeSession(), notes).ingest(_device(), flood.accepted, ip=None)  # type: ignore[arg-type]
    assert len(notes.sent) == MAX_NOTIFICATIONS_PER_REQUEST


@pytest.mark.parametrize("raw", [None, "", "not-a-key", "amd__secret", "xyz_abcd_secret"])
async def test_malformed_keys_are_refused_before_any_lookup(raw: str | None) -> None:
    with pytest.raises(AuthenticationFailed):
        await DeviceService(FakeSession()).authenticate(raw)  # type: ignore[arg-type]


async def test_created_key_has_the_documented_shape() -> None:
    session = FakeSession()
    _, key = await DeviceService(session).create(
        uuid4(), name=" Desk PC ", kind="desktop", created_by=uuid4()
    )  # type: ignore[arg-type]
    (model,) = session.added
    prefix = key.split("_")[1]
    assert key.startswith("amd_") and len(key) > 40
    assert model.key_prefix == prefix and model.name == "Desk PC"
    assert model.key_hash != key  # only the hash is stored


def test_device_status() -> None:
    device = _device()
    now = utc_now()
    assert device_status(device, now) == "never_seen"
    device.last_seen_at = now - timedelta(minutes=1)
    assert device_status(device, now) == "online"
    device.last_seen_at = now - timedelta(minutes=10)
    assert device_status(device, now) == "offline"
    device.revoked_at = now
    assert device_status(device, now) == "revoked"
