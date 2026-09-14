"""Transparent, bounded gzip request-body decompression.

The Raj Local Agent gzips large batch uploads (``Content-Encoding: gzip``).
Starlette/FastAPI decompress *responses* but not *requests*, so this small pure
ASGI middleware decompresses incoming gzip bodies before routing. It is a no-op
for every request that doesn't set ``Content-Encoding: gzip``, so existing
endpoints are unaffected.

**Bounded, deliberately.** The original implementation accumulated the whole
compressed body and then called ``gzip.decompress`` on it, with no ceiling on
either. Staging validation measured what that allows: a 203,910-byte request
expanded to 209,715,246 bytes in memory — about 1000:1 — and took 42 seconds to
refuse. The protocol limit that should have stopped it (monitoring.v1's 1 MiB
request ceiling) is applied to the *decompressed* body, so it cannot run until
the amplification has already happened.

So decompression streams through a ceiling instead. A body that exceeds it is
refused with 413 before the memory is committed, which turns an amplification
attack into an ordinary rejected request. The ceiling is a transport-level
backstop shared by every protocol behind it, set well above any legitimate
upload; each protocol still enforces its own, stricter, semantic limit.
"""

from __future__ import annotations

import json
import zlib

from starlette.types import ASGIApp, Message, Receive, Scope, Send

#: Transport backstop, not a protocol limit. It only has to be high enough never
#: to reject a legitimate upload, while keeping the memory a single request can
#: commit bounded and knowable. The largest legitimate body behind this
#: middleware is an EOD chunk at ``eod_max_chunk_bytes`` (25 MiB); the agent
#: protocol's batches are smaller, and monitoring.v1 enforces its own 1 MiB
#: ceiling on top of this one.
MAX_DECOMPRESSED_BYTES = 32 * 1024 * 1024

#: A compressed stream larger than this is refused without decompressing it at
#: all. No legitimate client sends more compressed bytes than the decompressed
#: ceiling allows.
MAX_COMPRESSED_BYTES = MAX_DECOMPRESSED_BYTES

# gzip (rather than raw deflate) window size for zlib.
_GZIP_WBITS = 16 + zlib.MAX_WBITS


class RequestTooLarge(Exception):
    """The request body exceeded the transport ceiling.

    Carries whether the client had already finished sending. Draining a stream
    that is already exhausted would block on a message that will never arrive,
    so the refusal path has to know which case it is in.
    """

    def __init__(self, detail: str, *, stream_exhausted: bool) -> None:
        super().__init__(detail)
        self.detail = detail
        self.stream_exhausted = stream_exhausted


class GzipRequestMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        max_decompressed_bytes: int = MAX_DECOMPRESSED_BYTES,
        max_compressed_bytes: int = MAX_COMPRESSED_BYTES,
    ) -> None:
        self.app = app
        self.max_decompressed_bytes = max_decompressed_bytes
        self.max_compressed_bytes = max_compressed_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {k.lower(): v for k, v in scope.get("headers", [])}
        if headers.get(b"content-encoding") != b"gzip":
            await self.app(scope, receive, send)
            return

        try:
            body = await self._read_bounded(receive)
        except RequestTooLarge as exc:
            # Drain the rest of the upload before answering, without buffering
            # it. Closing early would reach the client as a connection reset,
            # and under the retry contract a reset is retryable while 413 is
            # terminal — so an oversized message would be retried forever
            # instead of being reported as the permanent error it is. The
            # memory, which was the actual vulnerability, stays bounded either
            # way; only the bandwidth is spent.
            if not exc.stream_exhausted:
                await _drain(receive)
            await _refuse(send, exc.detail)
            return

        new_headers = [
            (k, v)
            for (k, v) in scope.get("headers", [])
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

    async def _read_bounded(self, receive: Receive) -> bytes:
        """Decompress the request body, refusing to exceed either ceiling.

        Decompression is incremental and capped per call, so an expanding stream
        is stopped at the ceiling rather than after it has been materialised.
        """
        decompressor = zlib.decompressobj(_GZIP_WBITS)
        compressed_seen = 0
        decompressed = bytearray()
        raw = bytearray()
        valid_gzip = True
        more_body = True

        while more_body:
            message: Message = await receive()
            chunk = message.get("body", b"")
            more_body = message.get("more_body", False)
            if not chunk:
                continue

            compressed_seen += len(chunk)
            if compressed_seen > self.max_compressed_bytes:
                raise RequestTooLarge(
                    f"compressed request body exceeds the {self.max_compressed_bytes} byte limit",
                    stream_exhausted=not more_body,
                )
            # Kept so an invalid-gzip body can still be passed through untouched,
            # which is the documented behaviour this middleware has always had.
            raw += chunk

            if not valid_gzip:
                continue

            try:
                # ``max_length`` bounds the output of this call; anything the
                # decompressor could not emit stays in unconsumed_tail, which is
                # exactly the signal that the ceiling has been reached.
                remaining = self.max_decompressed_bytes - len(decompressed) + 1
                decompressed += decompressor.decompress(chunk, remaining)
            except zlib.error:
                valid_gzip = False
                continue

            if len(decompressed) > self.max_decompressed_bytes:
                raise RequestTooLarge(
                    f"decompressed request body exceeds the "
                    f"{self.max_decompressed_bytes} byte limit",
                    stream_exhausted=not more_body,
                )

        if not valid_gzip:
            # Not valid gzip after all — pass through untouched.
            return bytes(raw)

        try:
            # Bounded like every other decompress call. An unbounded flush would
            # reopen the hole: input the ceiling stopped us consuming is still
            # sitting in ``unconsumed_tail``, and flushing it without a limit
            # would expand exactly the bytes we declined to expand above.
            decompressed += decompressor.flush(
                max(1, self.max_decompressed_bytes - len(decompressed) + 1)
            )
        except zlib.error:
            return bytes(raw)

        if len(decompressed) > self.max_decompressed_bytes:
            # Reached only after the loop ended, so the client has finished.
            raise RequestTooLarge(
                f"decompressed request body exceeds the {self.max_decompressed_bytes} byte limit",
                stream_exhausted=True,
            )
        return bytes(decompressed)


async def _drain(receive: Receive) -> None:
    """Consume and discard whatever remains of the request body.

    Bounded in memory by construction: each chunk is dropped as it arrives.
    """
    try:
        while True:
            message: Message = await receive()
            if message.get("type") == "http.disconnect":
                return
            if not message.get("more_body", False):
                return
    except Exception:
        return


async def _refuse(send: Send, detail: str) -> None:
    """Answer 413 from the middleware, before the application sees the body."""
    payload = json.dumps({"detail": {"reason": "request_too_large", "detail": detail}}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(payload)).encode("latin-1")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload, "more_body": False})
