"""Auth0 authentication helpers for MCP servers.

Verifies Auth0 access tokens, builds the caller, enforces scopes, and exchanges tokens
(On-Behalf-Of, client credentials, Token Vault) with an optional `token_store` for caching.
It owns no MCP framework, so each framework gets a thin adapter around it.
"""

from __future__ import annotations

from auth0_api_python import (
    AbstractTokenStore,
    ApiClient,
    ApiClientOptions,
    GetAccessTokenForConnectionError,
    GetClientCredentialsTokenError,
    IndexedTokenStore,
    TokenIndexMember,
    TokenSet,
    VerifiedToken,
)
from auth0_api_python.errors import (
    ApiError,
    AuthServerUnavailableError,
    ConfigurationError,
    GetTokenByExchangeProfileError,
    MissingOrganizationError,
    MissingRequiredArgumentError,
    OrganizationNotAllowedError,
    VerifyAccessTokenError,
)

from .client import McpServerClient, create_mcp_client
from .errors import (
    DownscopedTokenError,
    InsufficientScopeError,
    UnauthenticatedError,
)
from .principal import Principal, build_principal
from .request_context import (
    RequestContext,
    bind_request_context,
    get_caller_mcp_client,
    get_caller_principal,
    require_caller_mcp_client,
    require_caller_principal,
)
from .request_scoped_client import RequestScopedMcpClient
from .scopes import require_scopes, with_required_scopes

__all__ = [
    "AbstractTokenStore",
    "ApiClient",
    "ApiClientOptions",
    "ApiError",
    "AuthServerUnavailableError",
    "ConfigurationError",
    "DownscopedTokenError",
    "GetAccessTokenForConnectionError",
    "GetClientCredentialsTokenError",
    "GetTokenByExchangeProfileError",
    "IndexedTokenStore",
    "InsufficientScopeError",
    "McpServerClient",
    "MissingOrganizationError",
    "MissingRequiredArgumentError",
    "OrganizationNotAllowedError",
    "Principal",
    "RequestContext",
    "RequestScopedMcpClient",
    "TokenIndexMember",
    "TokenSet",
    "UnauthenticatedError",
    "VerifiedToken",
    "VerifyAccessTokenError",
    "bind_request_context",
    "build_principal",
    "create_mcp_client",
    "get_caller_mcp_client",
    "get_caller_principal",
    "require_caller_mcp_client",
    "require_caller_principal",
    "require_scopes",
    "with_required_scopes",
]
