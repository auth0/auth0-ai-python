"""Answers a failed token check caused by an Auth0 outage with 503 instead of FastMCP's 500."""

from __future__ import annotations

import json
import logging

from auth0_ai_mcp import AuthServerUnavailableError
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

_BODY = json.dumps(
    {
        "jsonrpc": "2.0",
        "error": {"code": -32002, "message": "Service unavailable: the token could not be verified"},
        "id": None,
    }
).encode()


class ServiceUnavailableMiddleware:
    """ASGI middleware that turns `AuthServerUnavailableError` into a 503 with `Retry-After`."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except AuthServerUnavailableError as exc:
            if started:
                raise
            logger.error("Auth0 could not be reached to verify the token: %r", str(exc))
            # No challenge, so the client keeps its token and retries instead of logging in again.
            headers = [(b"content-type", b"application/json"), (b"retry-after", b"5"), (b"cache-control", b"no-store")]
            await send({"type": "http.response.start", "status": 503, "headers": headers})
            await send({"type": "http.response.body", "body": _BODY})
