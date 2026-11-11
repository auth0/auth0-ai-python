"""Per-request state, reachable from tool code without threading arguments.

The adapter verifies the token and sets this contextvar before the MCP handler runs.
Tool code reads the caller and its request-scoped client from here, so a tool signature
stays clean and never has to accept an auth object it did not ask for.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .errors import UnauthenticatedError
from .principal import Principal

if TYPE_CHECKING:
    from .request_scoped_client import RequestScopedMcpClient


@dataclass
class RequestContext:
    """
    The per-request state that tool code reads.

    Attributes:
        principal: The verified caller for this request.
        mcp_client: The request-scoped client bound to that caller's token.
    """

    principal: Principal
    mcp_client: RequestScopedMcpClient


_request_context: ContextVar[RequestContext | None] = ContextVar(
    "auth0_ai_mcp_request_context", default=None
)


def set_request_context(context: RequestContext) -> Token[RequestContext | None]:
    """Set the current request context, returning the token to reset it after."""
    return _request_context.set(context)


def reset_request_context(token: Token[RequestContext | None]) -> None:
    """Reset the request context to its prior state."""
    _request_context.reset(token)


@contextmanager
def bind_request_context(context: RequestContext) -> Iterator[None]:
    """Set the request context for the duration of a `with` block.

    Args:
        context: The verified caller and request-scoped client for this request.

    Yields:
        None. The context is reset on exit, including when the block raises.
    """
    token = set_request_context(context)
    try:
        yield
    finally:
        reset_request_context(token)


def get_caller_principal() -> Principal | None:
    """Return the verified caller for this request, or None outside a request."""
    ctx = _request_context.get()
    return ctx.principal if ctx else None


def require_caller_principal() -> Principal:
    """Return the verified caller, raising if called outside a request."""
    principal = get_caller_principal()
    if principal is None:
        raise UnauthenticatedError("No principal in the current request context.")
    return principal


def get_caller_mcp_client() -> RequestScopedMcpClient | None:
    """Return the request-scoped client, or None outside a request."""
    ctx = _request_context.get()
    return ctx.mcp_client if ctx else None


def require_caller_mcp_client() -> RequestScopedMcpClient:
    """Return the request-scoped client, raising if called outside a request."""
    client = get_caller_mcp_client()
    if client is None:
        raise UnauthenticatedError("No MCP client in the current request context.")
    return client
