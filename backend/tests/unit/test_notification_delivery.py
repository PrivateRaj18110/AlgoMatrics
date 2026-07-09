"""Unit tests for pure notification delivery routing (Phase 15)."""

from __future__ import annotations

from datetime import time

from algo_platform.modules.notifications.domain.delivery import (
    Channel,
    DeliveryPreference,
    QuietHours,
    Severity,
    resolve_channels,
    severity_rank,
)


def test_severity_rank_orders_and_defaults_unknown_to_info() -> None:
    assert severity_rank("info") < severity_rank("warning") < severity_rank("critical")
    assert severity_rank("success") == 1
    assert severity_rank("nonsense") == 0


def test_default_preference_is_in_app_only() -> None:
    pref = DeliveryPreference()
    channels = resolve_channels(pref, type_="general", severity="critical")
    assert channels == frozenset({Channel.IN_APP})


def test_muted_type_yields_no_channels() -> None:
    pref = DeliveryPreference(
        enabled_channels=frozenset({Channel.IN_APP, Channel.EMAIL}),
        muted_types=frozenset({"marketing"}),
    )
    assert resolve_channels(pref, type_="marketing", severity="info") == frozenset()


def test_email_included_when_enabled_and_above_threshold() -> None:
    pref = DeliveryPreference(
        enabled_channels=frozenset({Channel.IN_APP, Channel.EMAIL, Channel.WEBHOOK}),
        min_severity=Severity.WARNING,
    )
    assert resolve_channels(pref, type_="order", severity="warning") == frozenset(
        {Channel.IN_APP, Channel.EMAIL, Channel.WEBHOOK}
    )


def test_below_min_severity_stays_in_app_only() -> None:
    pref = DeliveryPreference(
        enabled_channels=frozenset({Channel.IN_APP, Channel.EMAIL}),
        min_severity=Severity.WARNING,
    )
    assert resolve_channels(pref, type_="order", severity="info") == frozenset(
        {Channel.IN_APP}
    )


def test_in_app_always_present_even_if_not_enabled() -> None:
    pref = DeliveryPreference(enabled_channels=frozenset({Channel.EMAIL}))
    channels = resolve_channels(pref, type_="order", severity="info")
    assert Channel.IN_APP in channels
    assert Channel.EMAIL in channels


def test_quiet_hours_suppress_external_channels() -> None:
    pref = DeliveryPreference(
        enabled_channels=frozenset({Channel.IN_APP, Channel.EMAIL}),
        quiet_hours=QuietHours(start=time(22, 0), end=time(7, 0)),
    )
    at_night = resolve_channels(
        pref, type_="order", severity="warning", local_time=time(23, 30)
    )
    assert at_night == frozenset({Channel.IN_APP})
    daytime = resolve_channels(
        pref, type_="order", severity="warning", local_time=time(9, 0)
    )
    assert Channel.EMAIL in daytime


def test_critical_bypasses_quiet_hours_by_default() -> None:
    pref = DeliveryPreference(
        enabled_channels=frozenset({Channel.IN_APP, Channel.EMAIL}),
        quiet_hours=QuietHours(start=time(22, 0), end=time(7, 0)),
    )
    channels = resolve_channels(
        pref, type_="risk", severity="critical", local_time=time(2, 0)
    )
    assert Channel.EMAIL in channels


def test_critical_respects_quiet_hours_when_override_disabled() -> None:
    pref = DeliveryPreference(
        enabled_channels=frozenset({Channel.IN_APP, Channel.EMAIL}),
        quiet_hours=QuietHours(start=time(22, 0), end=time(7, 0)),
        critical_overrides_quiet=False,
    )
    channels = resolve_channels(
        pref, type_="risk", severity="critical", local_time=time(2, 0)
    )
    assert channels == frozenset({Channel.IN_APP})


def test_quiet_hours_empty_window_never_quiet() -> None:
    window = QuietHours(start=time(9, 0), end=time(9, 0))
    assert window.contains(time(9, 0)) is False
    assert window.contains(time(23, 0)) is False


def test_quiet_hours_non_wrapping_window() -> None:
    window = QuietHours(start=time(1, 0), end=time(6, 0))
    assert window.contains(time(3, 0)) is True
    assert window.contains(time(0, 30)) is False
    assert window.contains(time(6, 0)) is False
