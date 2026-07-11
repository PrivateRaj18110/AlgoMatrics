"""Transparent gzip request-body decompression.

The Raj Local Agent gzips large batch uploads (``Content-Encoding: gzip``).
Starlette/FastAPI decompress *responses* but not *requests*, so this small pure
ASGI middleware decompresses incoming gzip bodies before routing. It is a no-op
for every request that doesn't set ``Content-Encoding: gzip``, so existing
endpoints are unaffected.
"""

from __future__ import annotations

import gzip

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class GzipRequestMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        if headers.get(b"content-encoding") != b"gzip":
            await self.app(scope, receive, send)
            return

        # Drain and decompress the full body.
        body = b""
        more_body = True
        while more_body:
            message: Message = await receive()
            body += message.get("body", b"")
            more_body = message.get("more_body", False)

        try:
            body = gzip.decompress(body)
        except OSError:
            # Not valid gzip after all — pass through untouched.
            pass

        new_headers = [
            (k, v) for (k, v) in scope.get("headers", [])
            if k.lower() not in (b"content-encoding", b"content-length")
        ]
        new_headers.append((b"content-length", str(len(body)).encode("latin-1")))
        new_scope = dict(scope)
        new_scope["headers"] = new_headers

        sent = False

        async def patched_receive() -> Message:
            nonlocal sent
            if sent:
                return {"type": "http.disconnect"}
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        await self.app(new_scope, patched_receive, send)
