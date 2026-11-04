"""Request context for FastMCP servers."""

from __future__ import annotations

from typing import Any

from auth0_ai_mcp import (
    ApiError,
    DownscopedTokenError,
    McpServerClient,
    RequestContext,
    UnauthenticatedError,
    VerifiedToken,
    bind_request_context,
    build_principal,
)
from fastmcp.exceptions import FastMCPError, PromptError, ResourceError, ToolError
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext

_METHODS_WITHOUT_CALLER = frozenset({"initialize", "ping"})


def _exchange_failure(exc: FastMCPError, wrapper_prefix: str) -> FastMCPError | None:
    """Return the error code only version of `exc` if FastMCP wrapped a failed token exchange, else None."""
    cause = exc.__cause__
    # FastMCP's own wrapper message starts with this prefix, a handler's own error does not.
    if isinstance(cause, ApiError | DownscopedTokenError) and str(exc).startswith(wrapper_prefix):
        return type(exc)(f"Token exchange failed ({cause.get_error_code()})")
    return None


class Auth0ContextMiddleware(Middleware):
    """Makes the verified caller available to tools, resources and prompts.

    Inside a handler, `get_caller_principal()` and `get_caller_mcp_client()` return the caller's identity and a client bound to their token.

    Args:
        mcp_client: The client used to build the request-scoped client for each caller.
    """

    def __init__(self, mcp_client: McpServerClient) -> None:
        super().__init__()
        self._client = mcp_client

    async def on_request(self, context: MiddlewareContext[Any], call_next: CallNext[Any, Any]) -> Any:
        """Bind the verified caller for the duration of the request.

        Raises:
            UnauthenticatedError: If the request has no verified token. `initialize` and
                `ping` are exempt because they carry no caller.
            VerifyAccessTokenError: If `build_principal` rejects the verified claims, for example a missing `sub`, `exp` or client id.
                `Auth0TokenVerifier` already rejects those, so this only fires with a different verifier.
        """
        access_token = get_access_token()
        if access_token is None:
            if context.method in _METHODS_WITHOUT_CALLER:
                return await call_next(context)
            raise UnauthenticatedError("No verified access token on this request")
        verified = VerifiedToken(access_token=access_token.token, claims=access_token.claims or {})
        principal = build_principal(verified.claims)
        request_context = RequestContext(
            principal=principal,
            mcp_client=self._client.with_token(verified, principal),
        )
        with bind_request_context(request_context):
            return await call_next(context)

    async def on_call_tool(self, context: MiddlewareContext[Any], call_next: CallNext[Any, Any]) -> Any:
        """Replace the error text of a failed token exchange with its error code.

        Raises:
            ToolError: `Token exchange failed (<error code>)` when a tool lets an `ApiError` or `DownscopedTokenError` escape. A `ToolError` the tool raises itself passes through unchanged.
        """
        try:
            return await call_next(context)
        except ToolError as exc:
            if (replacement := _exchange_failure(exc, f"Error calling tool {context.message.name!r}")) is not None:
                raise replacement from exc.__cause__
            raise

    async def on_read_resource(self, context: MiddlewareContext[Any], call_next: CallNext[Any, Any]) -> Any:
        """Replace the error text of a failed token exchange with its error code.

        Raises:
            ResourceError: `Token exchange failed (<error code>)` when a resource lets an `ApiError` or `DownscopedTokenError` escape. A `ResourceError` the resource raises itself passes through unchanged.
        """
        try:
            return await call_next(context)
        except ResourceError as exc:
            if (replacement := _exchange_failure(exc, f"Error reading resource {str(context.message.uri)!r}")) is not None:
                raise replacement from exc.__cause__
            raise

    async def on_get_prompt(self, context: MiddlewareContext[Any], call_next: CallNext[Any, Any]) -> Any:
        """Replace the error text of a failed token exchange with its error code.

        Raises:
            PromptError: `Token exchange failed (<error code>)` when a prompt lets an `ApiError` or `DownscopedTokenError` escape. A `PromptError` the prompt raises itself passes through unchanged.
        """
        try:
            return await call_next(context)
        except PromptError as exc:
            if (replacement := _exchange_failure(exc, f"Error rendering prompt {context.message.name!r}")) is not None:
                raise replacement from exc.__cause__
            raise
