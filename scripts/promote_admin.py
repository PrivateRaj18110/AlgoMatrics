"""Promote (or demote) a user to platform administrator.

Usage:
    uv run python scripts/promote_admin.py user@example.com [--revoke]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))

from sqlalchemy import select

from algo_platform.config import get_settings
from algo_platform.modules.identity.infrastructure.models import UserModel
from algo_platform.shared.infrastructure.database import (
    create_engine,
    create_session_factory,
)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("email")
    parser.add_argument("--revoke", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.database_url, pool_size=1)
    session_factory = create_session_factory(engine)
    async with session_factory() as session:
        user = (
            await session.execute(
                select(UserModel).where(UserModel.email == args.email.strip().lower())
            )
        ).scalar_one_or_none()
        if user is None:
            print(f"no user with e-mail {args.email}")
            return 1
        user.is_platform_admin = not args.revoke
        await session.commit()
    await engine.dispose()
    verb = "revoked from" if args.revoke else "granted to"
    print(f"platform admin {verb} {args.email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
