"""Read/write a recipient's notification delivery preferences."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from algo_platform.modules.notifications.domain.delivery import (
    Channel,
    DeliveryPreference,
    QuietHours,
    Severity,
)
from algo_platform.modules.notifications.infrastructure.channels import validate_webhook_url
from algo_platform.modules.notifications.infrastructure.models import (
    NotificationPreferenceModel,
)
from algo_platform.shared.domain.types import utc_now


@dataclass(frozen=True, slots=True)
class PreferenceDTO:
    enabled_channels: list[str]
    muted_types: list[str]
    min_severity: str
    quiet_start: time | None
    quiet_end: time | None
    critical_overrides_quiet: bool
    webhook_url: str | None


def _to_domain(model: NotificationPreferenceModel) -> DeliveryPreference:
    channels = frozenset(_coerce_channels(model.enabled_channels))
    quiet = (
        QuietHours(start=model.quiet_start, end=model.quiet_end)
        if model.quiet_start is not None and model.quiet_end is not None
        else None
    )
    return DeliveryPreference(
        enabled_channels=channels or frozenset({Channel.IN_APP}),
        muted_types=frozenset(model.muted_types),
        min_severity=_coerce_severity(model.min_severity),
        quiet_hours=quiet,
        critical_overrides_quiet=model.critical_overrides_quiet,
    )


def _coerce_channels(values: list[str]) -> set[Channel]:
    out: set[Channel] = set()
    for value in values:
        try:
            out.add(Channel(value))
        except ValueError:
            continue
    return out


def _coerce_severity(value: str) -> Severity:
    try:
        return Severity(value)
    except ValueError:
        return Severity.INFO


class NotificationPreferenceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _get_model(
        self, organization_id: UUID, user_id: UUID
    ) -> NotificationPreferenceModel | None:
        return (
            await self._session.execute(
                select(NotificationPreferenceModel).where(
                    NotificationPreferenceModel.organization_id == organization_id,
                    NotificationPreferenceModel.user_id == user_id,
                )
            )
        ).scalar_one_or_none()

    async def resolve(self, organization_id: UUID, user_id: UUID) -> DeliveryPreference:
        """Domain preference for routing; defaults (in-app only) if unset."""

        model = await self._get_model(organization_id, user_id)
        return _to_domain(model) if model is not None else DeliveryPreference()

    async def get(self, organization_id: UUID, user_id: UUID) -> PreferenceDTO:
        model = await self._get_model(organization_id, user_id)
        if model is None:
            return PreferenceDTO(
                enabled_channels=["in_app"],
                muted_types=[],
                min_severity="info",
                quiet_start=None,
                quiet_end=None,
                critical_overrides_quiet=True,
                webhook_url=None,
            )
        return PreferenceDTO(
            enabled_channels=list(model.enabled_channels),
            muted_types=list(model.muted_types),
            min_severity=model.min_severity,
            quiet_start=model.quiet_start,
            quiet_end=model.quiet_end,
            critical_overrides_quiet=model.critical_overrides_quiet,
            webhook_url=model.webhook_url,
        )

    async def update(
        self,
        organization_id: UUID,
        user_id: UUID,
        *,
        enabled_channels: list[str],
        muted_types: list[str],
        min_severity: str,
        quiet_start: time | None,
        quiet_end: time | None,
        critical_overrides_quiet: bool,
        webhook_url: str | None,
    ) -> PreferenceDTO:
        channels = sorted(c.value for c in _coerce_channels(enabled_channels)) or ["in_app"]
        severity = _coerce_severity(min_severity).value
        if webhook_url:
            validate_webhook_url(webhook_url)  # raises ValidationFailed on SSRF/non-https
        model = await self._get_model(organization_id, user_id)
        if model is None:
            model = NotificationPreferenceModel(
                organization_id=organization_id, user_id=user_id, updated_at=utc_now()
            )
            self._session.add(model)
        model.enabled_channels = channels
        model.muted_types = list(muted_types)
        model.min_severity = severity
        model.quiet_start = quiet_start
        model.quiet_end = quiet_end
        model.critical_overrides_quiet = critical_overrides_quiet
        model.webhook_url = webhook_url or None
        model.updated_at = utc_now()
        await self._session.flush()
        return await self.get(organization_id, user_id)
