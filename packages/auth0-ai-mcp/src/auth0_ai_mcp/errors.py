"""Errors owned by auth0-ai-mcp.

The core SDK (auth0-api-python) owns errors for the functions it provides, and this
package raises those directly. These are the errors with no core equivalent. They all
extend BaseAuthError so a caller can catch one base type across both layers.
"""

from __future__ import annotations

from auth0_api_python.errors import BaseAuthError


class UnauthenticatedError(BaseAuthError):
    """No verified caller in the current request context. Raised inside the tool, so the framework reports it as a tool error."""

    def get_status_code(self) -> int:
        return 401

    def get_error_code(self) -> str:
        return "invalid_token"


class InsufficientScopeError(BaseAuthError):
    """The caller's token is missing a required scope. Raised inside the tool, so the framework reports it as a tool error."""

    def get_status_code(self) -> int:
        return 403

    def get_error_code(self) -> str:
        return "insufficient_scope"


class DownscopedTokenError(BaseAuthError):
    """The exchange granted fewer scopes than were requested. Error code `downscoped_token`, status 403."""

    def get_status_code(self) -> int:
        return 403

    def get_error_code(self) -> str:
        return "downscoped_token"
