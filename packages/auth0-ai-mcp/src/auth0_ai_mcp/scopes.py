"""Scope-gating decorator for async MCP tool handlers.

`with_required_scopes` checks the incoming MCP token's scopes before the tool body
runs and raises if the caller is missing any of the requested scopes. It reads the
verified caller from the request context the adapter set up, so the tool body does
not receive an auth argument.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from .errors import InsufficientScopeError, UnauthenticatedError
from .principal import Principal
from .request_context import get_caller_principal
from .utils._internal import scope_input

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Awaitable[object]])


def require_scopes(principal: Principal | None, scopes: str | list[str]) -> None:
    """Raise if the principal is missing any of the given scopes.

    Args:
        principal: The verified caller, or None when there is no request context.
        scopes: A single required scope, or a list of scopes that must all be present.

    Raises:
        ConfigurationError: If `scopes` is empty, blank, or holds a non-string or blank entry.
        UnauthenticatedError: If `principal` is None.
        InsufficientScopeError: If the principal is missing any required scope.
    """
    required = scope_input.normalize_scopes(scopes)
    if principal is None:
        raise UnauthenticatedError("No principal in the current request context.")
    logger.debug("Token scopes: %s, required: %s", principal.scopes, required)
    if any(s not in principal.scopes for s in required):
        logger.info("Scope check failed. The token is missing one or more required scopes.")
        raise InsufficientScopeError("Missing one or more required scopes.")


def with_required_scopes(scopes: str | list[str]) -> Callable[[F], F]:
    """Return a decorator that gates an async handler on the given scopes.

    Args:
        scopes: A single required scope, or a list of scopes that must all be present.

    Returns:
        A decorator that runs the scope check before the handler body.

    Raises:
        ConfigurationError: At decoration time, if `scopes` is empty, blank, or holds a non-string or blank entry.
    """
    required = scope_input.normalize_scopes(scopes)

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: object, **kwargs: object) -> object:
            require_scopes(get_caller_principal(), required)
            return await func(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator
