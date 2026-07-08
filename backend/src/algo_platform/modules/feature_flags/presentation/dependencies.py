"""Route-level feature gate: ``dependencies=[Depends(require_feature("live_trading"))]``."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from algo_platform.api.dependencies.core import RedisDep, SessionDep, SettingsDep
from algo_platform.api.dependencies.tenant import TenantDep
from algo_platform.modules.feature_flags.application.service import FeatureFlagService
from algo_platform.modules.feature_flags.domain.flags import EvaluationContext
from algo_platform.shared.domain.errors import PermissionDenied


def require_feature(key: str) -> Callable[..., Coroutine[Any, Any, None]]:
    """Build a dependency that denies the request when ``key`` is off for the caller."""

    async def dependency(
        tenant: TenantDep, session: SessionDep, redis: RedisDep, settings: SettingsDep
    ) -> None:
        service = FeatureFlagService(session, redis)
        context = EvaluationContext(
            environment=settings.app_env,
            organization_id=tenant.organization_id,
            user_id=tenant.user.user_id,
        )
        if not await service.is_enabled(key, context):
            raise PermissionDenied(f"feature '{key}' is not enabled for this account")

    return dependency
