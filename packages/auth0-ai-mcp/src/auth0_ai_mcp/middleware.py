"""ASGI middleware: wires Auth0 verification into any Starlette/FastAPI or official MCP app.

The middleware verifies the incoming bearer token, builds the caller's Principal, and sets
the request context before the MCP handler runs, so tool code reaches the caller through
`get_caller_principal()` / `require_caller_mcp_client()`. A missing or invalid token
gets a 401 with a `WWW-Authenticate` challenge and never reaches a tool. If Auth0 cannot be reached
to verify the token, the response is a 503 without a challenge. It also serves the RFC 9728
`/.well-known/oauth-protected-resource` metadata document, at the root and at the path derived
from the resource URL. WebSocket connections are refused.
"""

from __future__ import annotations

import json
import logging
from urllib.parse import urlsplit

from auth0_api_python.errors import (
    AuthServerUnavailableError,
    VerifyAccessTokenError,
)
from starlette.authentication import AuthCredentials
from starlette.types import ASGIApp, Receive, Scope, Send

from .client import McpServerClient
from .principal import build_principal
from .request_context import RequestContext, bind_request_context
from .utils._internal import headers, mcp_session, urls

logger = logging.getLogger(__name__)

_PRM_PATH = "/.well-known/oauth-protected-resource"
_INVALID_DESCRIPTION = "The access token is not valid"


def build_protected_resource_metadata(
    mcp_client: McpServerClient,
    *,
    resource_url: str | None = None,
    authorization_servers: list[str] | None = None,
    scopes_supported: list[str] | None = None,
    resource_name: str | None = None,
    resource_documentation: str | None = None,
) -> dict:
    """Build the RFC 9728 protected-resource metadata document.

    Args:
        mcp_client: The server client. Its audience is the default `resource_url` and its domain the default authorization server.
        resource_url: Absolute http or https URL of the protected resource. Defaults to the client audience and must equal it when given.
        authorization_servers: Issuer URLs to advertise, each an absolute https URL. Defaults to the client's tenant domain and is required when the client has no single domain.
        scopes_supported: Optional scopes to advertise. Omitted from the document when None.
        resource_name: Optional human-readable name for the resource. Omitted from the document when None.
        resource_documentation: Optional URL of documentation for the resource. Omitted from the document when None.

    Returns:
        The metadata document as a dict.

    Raises:
        ConfigurationError: If `resource_url` differs from the client audience or is not an absolute http or https URL, or if `authorization_servers` cannot be resolved or holds anything but absolute https URLs.
    """
    doc: dict = {
        "resource": urls.resolve_resource_url(mcp_client, resource_url),
        "authorization_servers": urls.resolve_authorization_servers(mcp_client, authorization_servers),
        "bearer_methods_supported": ["header"],
    }
    if scopes_supported is not None:
        doc["scopes_supported"] = scopes_supported
    if resource_name is not None:
        doc["resource_name"] = resource_name
    if resource_documentation is not None:
        doc["resource_documentation"] = resource_documentation
    return doc


def build_www_authenticate(
    resource_metadata_url: str, error: str | None = None, error_description: str | None = None
) -> str:
    """Build a Bearer `WWW-Authenticate` challenge with every value made safe for a quoted header.

    Args:
        resource_metadata_url: URL of the protected-resource metadata document.
        error: Optional RFC 6750 error code. Leave None when the request carried no token.
        error_description: Optional human-readable description, only sent alongside `error`.

    Returns:
        The challenge, ASCII only, for example `Bearer resource_metadata="https://host/.well-known/oauth-protected-resource"`.
    """
    params = []
    if error is not None:
        params.append(f'error="{headers.header_safe(error)}"')
        if error_description is not None:
            params.append(f'error_description="{headers.header_safe(error_description)}"')
    params.append(f'resource_metadata="{headers.header_safe(resource_metadata_url)}"')
    return "Bearer " + ", ".join(params)


class Auth0AsgiMiddleware:
    """Verifies the bearer token and populates the request context for each request.

    Args:
        app: The ASGI app to protect.
        mcp_client: The server client that verifies tokens.
        resource_url: Absolute http or https URL of the protected resource. Defaults to the client audience and must equal it when given.
        authorization_servers: Issuer URLs to advertise, each an absolute https URL. Defaults to the client's tenant domain and is required when the client has no single domain.
        scopes_supported: Optional scopes to advertise in the metadata document.
        resource_name: Optional human-readable name for the resource, advertised in the metadata document.
        resource_documentation: Optional URL of documentation for the resource, advertised in the metadata document.

    Raises:
        ConfigurationError: If `resource_url` differs from the client audience or is not an absolute http or https URL, or if `authorization_servers` cannot be resolved or holds anything but absolute https URLs.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        mcp_client: McpServerClient,
        resource_url: str | None = None,
        authorization_servers: list[str] | None = None,
        scopes_supported: list[str] | None = None,
        resource_name: str | None = None,
        resource_documentation: str | None = None,
    ):
        self._app = app
        self._client = mcp_client
        self._metadata = build_protected_resource_metadata(
            mcp_client,
            resource_url=resource_url,
            authorization_servers=authorization_servers,
            scopes_supported=scopes_supported,
            resource_name=resource_name,
            resource_documentation=resource_documentation,
        )
        parts = urlsplit(self._metadata["resource"])
        suffixed_path = _PRM_PATH + urls.resource_path(parts.path)
        self._metadata_paths = {_PRM_PATH, suffixed_path}
        self._metadata_url = f"{parts.scheme}://{parts.netloc}{suffixed_path}"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        method = scope.get("method")
        if method == "GET" and scope["path"] in self._metadata_paths:
            await self._send_json(send, 200, self._metadata)
            return

        # Browsers send a CORS preflight without credentials, so it cannot be verified.
        if method == "OPTIONS":
            await self._app(scope, receive, send)
            return

        token = headers.bearer_token(scope)
        if token is None:
            await self._send_unauthorized(send)
            return

        try:
            verified = await self._client.verify_access_token(token)
            principal = build_principal(verified.claims)
        except AuthServerUnavailableError as exc:
            logger.error("Auth0 could not be reached to verify the token: %s", exc)
            await self._send_unavailable(send)
            return
        except VerifyAccessTokenError as exc:
            logger.warning("Token rejected: %s", exc)
            await self._send_unauthorized(send, error="invalid_token")
            return

        context = RequestContext(
            principal=principal,
            mcp_client=self._client.with_token(verified, principal),
        )
        if mcp_session.AuthenticatedUser is not None:
            scope["user"] = mcp_session.AuthenticatedUser(mcp_session.access_token_info(principal, verified.claims))
            scope["auth"] = AuthCredentials(principal.scopes)
        with bind_request_context(context):
            await self._app(scope, receive, send)

    async def _send_json(
        self, send: Send, status: int, body: dict, headers: list[tuple[bytes, bytes]] | None = None
    ) -> None:
        raw = json.dumps(body).encode()
        response_headers = [(b"content-type", b"application/json")]
        if headers:
            response_headers.extend(headers)
        await send(
            {"type": "http.response.start", "status": status, "headers": response_headers}
        )
        await send({"type": "http.response.body", "body": raw})

    async def _send_unauthorized(self, send: Send, error: str | None = None) -> None:
        if error is None:
            challenge = build_www_authenticate(self._metadata_url)
            message = "Unauthorized"
        else:
            challenge = build_www_authenticate(self._metadata_url, error, _INVALID_DESCRIPTION)
            message = f"Unauthorized: {_INVALID_DESCRIPTION}"
        payload = {
            "jsonrpc": "2.0",
            "error": {"code": -32001, "message": message},
            "id": None,
        }
        await self._send_json(
            send, 401, payload, headers=[(b"www-authenticate", challenge.encode("ascii"))]
        )

    async def _send_unavailable(self, send: Send) -> None:
        # No challenge, so the client keeps its token and retries instead of logging in again.
        payload = {
            "jsonrpc": "2.0",
            "error": {"code": -32002, "message": "Service unavailable: the token could not be verified"},
            "id": None,
        }
        await self._send_json(send, 503, payload, headers=[(b"retry-after", b"5")])
