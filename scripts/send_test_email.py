"""Send a test e-mail through the configured EMAIL_BACKEND.

Verifies SMTP credentials and DNS deliverability end to end — run it after
setting EMAIL_BACKEND=smtp so registration/verification mails are known to
work before a real user hits them.

Local:
    uv run python scripts/send_test_email.py you@example.com

Production VM (compose):
    sudo docker compose -f deploy/compose/docker-compose.yml exec api \
        python scripts/send_test_email.py you@example.com
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))

from algo_platform.config import get_settings
from algo_platform.shared.application.ports import EmailMessage
from algo_platform.shared.infrastructure.email import create_email_sender


async def main() -> None:
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        print("usage: python scripts/send_test_email.py <recipient>")
        raise SystemExit(2)
    recipient = sys.argv[1].strip()
    settings = get_settings()
    sender = create_email_sender(settings)
    await sender.send(
        EmailMessage(
            to=recipient,
            subject="Algo Matrics — test e-mail",
            text=(
                "This is a test e-mail from your Algo Matrics deployment.\n\n"
                f"backend={settings.email_backend} from={settings.email_from}\n"
                f"app_base_url={settings.app_base_url}\n\n"
                "If this landed in spam, check the SPF/DKIM records for the "
                "sending domain."
            ),
        )
    )
    print(
        f"sent to {recipient} via EMAIL_BACKEND={settings.email_backend} "
        f"(from: {settings.email_from})"
    )
    if settings.email_backend == "console":
        print("NOTE: console backend only logs the message — nothing was delivered.")


if __name__ == "__main__":
    asyncio.run(main())
