from __future__ import annotations

import pytest

from algo_platform.modules.identity.presentation.auth_router import register
from algo_platform.modules.identity.presentation.schemas import RegisterRequest
from algo_platform.modules.workspace.application.service import WorkspaceTaskService
from algo_platform.shared.domain.errors import PermissionDenied, ValidationFailed


@pytest.mark.asyncio
async def test_public_register_http_is_disabled() -> None:
    with pytest.raises(PermissionDenied, match="public signup is disabled"):
        await register(
            RegisterRequest(
                email="owner@example.com",
                password="not-a-browser-secret",
                full_name="Owner",
            )
        )


@pytest.mark.asyncio
async def test_task_create_rejects_blank_title() -> None:
    service = WorkspaceTaskService(session=None)  # type: ignore[arg-type]
    with pytest.raises(ValidationFailed):
        await service.create("org", "user", title="   ")  # type: ignore[arg-type]
