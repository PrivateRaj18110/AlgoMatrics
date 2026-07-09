"""Default push provider: logs instead of calling an external service.

Keeps the platform fully functional and hermetic without APNs/FCM credentials.
Reports every target as delivered and prunes nothing.
"""

from __future__ import annotations

import structlog

from algo_platform.modules.mobile.application.ports import PushProvider, PushResult, PushTarget
from algo_platform.modules.mobile.domain.devices import PushMessage

logger = structlog.get_logger(__name__)


class NullPushProvider(PushProvider):
    async def send(self, message: PushMessage, targets: list[PushTarget]) -> PushResult:
        for target in targets:
            logger.info(
                "mobile.push_console_delivery",
                platform=target.platform.value,
                title=message.title,
            )
        return PushResult(delivered=len(targets))
