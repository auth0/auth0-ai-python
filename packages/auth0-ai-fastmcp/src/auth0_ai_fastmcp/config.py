"""Auth0 configuration for Prefect FastMCP servers."""

from __future__ import annotations

from dataclasses import dataclass, field

from auth0_ai_mcp import AbstractTokenStore, McpServerClient, create_mcp_client
from fastmcp.server.auth.providers.auth0 import Auth0MCPProvider
from starlette.middleware import Middleware

from .middleware import Auth0ContextMiddleware
from .utils._internal import outage, telemetry, validation
from .verifier import Auth0TokenVerifier


@dataclass
class Auth0FastMCPOptions:
    """Configuration for an Auth0-secured Prefect FastMCP server.

    Args:
        domain: Auth0 tenant domain with no scheme, e.g. "your-tenant.auth0.com".
        resource_url: Base URL of this server, without the MCP path. FastMCP appends the MCP path to it to advertise the resource.
        audience: This server's API identifier in Auth0. Defaults to resource_url plus mcp_path and must equal that value when set.
        mcp_path: Path the MCP endpoint is mounted at. Set it when the server is not served at "/mcp".
        tool_scopes: Scopes advertised in the metadata so the client requests them at login. `required_scopes` are advertised too.
        client_id: Needed for the on-behalf-of exchange, client credentials tokens and Token Vault. Token verification works without it.
        client_secret: Needed alongside `client_id` for the same flows.
        token_store: Backing store for cached OBO tokens. Nothing is cached without one.
        scope_matching: OBO cache scope-matching mode, "strict" or "non_strict".
        organization_policy: "allow" or "required".
        organization_id: Organization id or ids accepted when the policy is "required".
        required_scopes: Scopes required on every request. Tokens missing any of them are rejected.
    """

    domain: str
    resource_url: str
    audience: str | None = None
    mcp_path: str = "/mcp"
    tool_scopes: list[str] = field(default_factory=list)
    client_id: str | None = None
    client_secret: str | None = field(default=None, repr=False)
    token_store: AbstractTokenStore | None = None
    scope_matching: str = "strict"
    organization_policy: str = "allow"
    organization_id: str | list[str] | None = None
    required_scopes: list[str] | None = None


class _Auth0Provider(Auth0MCPProvider):
    def get_middleware(self) -> list:
        return [Middleware(outage.ServiceUnavailableMiddleware), *super().get_middleware()]


class Auth0FastMCP:
    """Builds the McpServerClient, FastMCP auth provider, and context middleware from options.

    The constructor fetches the tenant's OIDC discovery document, so an unreachable `domain` raises the HTTP client's connection error here.

    Raises:
        ConfigurationError: If `domain` is not a bare host, or `resource_url` is not an absolute http or https URL or holds a query, fragment or credentials.
        ConfigurationError: If `mcp_path` does not start with "/" or holds a query or fragment, or `audience` differs from `resource_url` plus `mcp_path`.
        ConfigurationError: If the core client rejects the options (for example `organization_id` with policy "allow"), or FastMCP is later given a different path than `mcp_path`.
    """

    def __init__(self, options: Auth0FastMCPOptions) -> None:
        self._options = options
        validation.require_bare_domain(options.domain)
        audience = validation.resolve_audience(options)
        self._mcp_client = create_mcp_client(
            options.domain,
            audience,
            client_id=options.client_id,
            client_secret=options.client_secret,
            token_store=options.token_store,
            scope_matching=options.scope_matching,
            organization_policy=options.organization_policy,
            organization_id=options.organization_id,
            client_info={
                "name": "auth0-ai-fastmcp",
                "version": telemetry.package_version("auth0-ai-fastmcp"),
                "env": {"fastmcp": telemetry.package_version("fastmcp")},
            },
        )
        self._provider = _Auth0Provider(
            config_url=f"https://{options.domain}/.well-known/openid-configuration",
            base_url=options.resource_url,
            resource_base_url=options.resource_url,
            scopes_supported=list(dict.fromkeys([*options.tool_scopes, *(options.required_scopes or [])])),
            token_verifier=Auth0TokenVerifier(
                self._mcp_client, required_scopes=options.required_scopes
            ),
        )
        validation.require_mounted_at_audience(self._provider, options.resource_url, audience)
        self._middleware = Auth0ContextMiddleware(self._mcp_client)

    @property
    def mcp_client(self) -> McpServerClient:
        """The underlying auth0-ai-mcp client."""
        return self._mcp_client

    @property
    def provider(self) -> Auth0MCPProvider:
        """The FastMCP auth provider to pass as FastMCP(auth=...)."""
        return self._provider

    @property
    def middleware(self) -> Auth0ContextMiddleware:
        """The middleware to register with mcp.add_middleware(...)."""
        return self._middleware

