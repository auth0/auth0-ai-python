"""Scope checks for FastMCP handlers.

These wrap `require_scopes` and `with_required_scopes` from auth0-ai-mcp so a denied call
reaches FastMCP as a tool error. The client then sees the reason, even with
`mask_error_details` on, and the server logs the denial at INFO instead of ERROR.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from auth0_ai_mcp import (
    InsufficientScopeError,
    Principal,
    UnauthenticatedError,
)
from auth0_ai_mcp import require_scopes as _require_scopes
from auth0_ai_mcp import with_required_scopes as _with_required_scopes
from fastmcp.exceptions import ToolError

F = TypeVar("F", bound=Callable[..., Awaitable[object]])


class _InsufficientScopeToolError(InsufficientScopeError, ToolError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.log_level = logging.INFO


class _UnauthenticatedToolError(UnauthenticatedError, ToolError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.log_level = logging.INFO


def _as_tool_error(exc: InsufficientScopeError | UnauthenticatedError) -> ToolError:
    error_type = _InsufficientScopeToolError if isinstance(exc, InsufficientScopeError) else _UnauthenticatedToolError
    return error_type(str(exc))


def require_scopes(principal: Principal | None, scopes: str | list[str]) -> None:
    """Raise if the principal is missing any of the given scopes.

    Args:
        principal: The verified caller, or None when there is no request context.
        scopes: A single required scope, or a list of scopes that must all be present.

    Raises:
        ConfigurationError: If `scopes` is empty, blank, or holds a non-string, blank or whitespace-containing entry.
        UnauthenticatedError: If `principal` is None. Also a FastMCP `ToolError`.
        InsufficientScopeError: If the principal is missing any required scope. Also a FastMCP `ToolError`.
    """
    try:
        _require_scopes(principal, scopes)
    except (InsufficientScopeError, UnauthenticatedError) as exc:
        raise _as_tool_error(exc) from exc


def with_required_scopes(scopes: str | list[str]) -> Callable[[F], F]:
    """Return a decorator that gates an async handler on the given scopes.

    Put the FastMCP registration decorator, such as `@mcp.tool`, above this one. Registered the other way round, FastMCP keeps the unguarded function and the check is skipped. Only async handlers can be gated.

    Args:
        scopes: A single required scope, or a list of scopes that must all be present.

    Returns:
        A decorator that runs the scope check before the handler body.

    Raises:
        ConfigurationError: At decoration time, if `scopes` is empty, blank, or holds a non-string, blank or whitespace-containing entry, or if the decorated function is not async.
    """
    guard = _with_required_scopes(scopes)

    def decorator(func: F) -> F:
        guarded = guard(func)

        @functools.wraps(func)
        async def wrapper(*args: object, **kwargs: object) -> object:
            try:
                return await guarded(*args, **kwargs)
            except (InsufficientScopeError, UnauthenticatedError) as exc:
                raise _as_tool_error(exc) from exc

        return wrapper  # type: ignore[return-value]

    return decorator
