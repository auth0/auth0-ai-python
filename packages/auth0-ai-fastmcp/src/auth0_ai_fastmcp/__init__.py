"""Auth0 integration for Prefect FastMCP servers."""

from .config import Auth0FastMCP, Auth0FastMCPOptions
from .middleware import Auth0ContextMiddleware
from .scopes import require_scopes, with_required_scopes
from .verifier import Auth0TokenVerifier

__all__ = [
    "Auth0ContextMiddleware",
    "Auth0FastMCP",
    "Auth0FastMCPOptions",
    "Auth0TokenVerifier",
    "require_scopes",
    "with_required_scopes",
]
