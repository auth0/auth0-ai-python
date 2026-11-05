from __future__ import annotations

from typing import TYPE_CHECKING

from auth0_ai_mcp import ConfigurationError
from pydantic import AnyHttpUrl, ValidationError

if TYPE_CHECKING:
    from fastmcp.server.auth.providers.auth0 import Auth0MCPProvider


def require_bare_domain(domain: str) -> None:
    """Reject a domain that FastMCP and the core client could not build their URLs from."""
    if not domain or any(ch in "/?#@" or ch.isspace() for ch in domain):
        raise ConfigurationError("domain must be a bare host such as tenant.auth0.com, with no scheme, path, query or whitespace")


def require_scope_list(name: str, scopes: object) -> None:
    """Reject a scope list that would be advertised or enforced wrongly, such as a bare string or an entry holding a space."""
    if not isinstance(scopes, list):
        raise ConfigurationError(f"{name} must be a list of scope strings")
    for scope in scopes:
        if not isinstance(scope, str) or not scope or any(ch.isspace() for ch in scope):
            raise ConfigurationError(f"{name} entries must be non-empty strings with no whitespace, so pass one scope per entry")


def resolve_audience(resource_url: str, mcp_path: str, audience: str | None) -> str:
    """Return the audience, defaulting to the resource FastMCP advertises, which tokens must carry as `aud`."""
    try:
        base = AnyHttpUrl(resource_url)
    except (ValidationError, TypeError) as exc:
        raise ConfigurationError("resource_url must be an absolute http or https URL with a host") from exc
    if base.query or base.fragment or base.username is not None or base.password is not None:
        raise ConfigurationError("resource_url must not contain a query, fragment or credentials")
    if not mcp_path.startswith("/") or "?" in mcp_path or "#" in mcp_path:
        raise ConfigurationError('mcp_path must start with "/" and hold no query or fragment')
    advertised = resource_at(resource_url, mcp_path)
    if audience is not None and audience != advertised:
        raise ConfigurationError(
            f"audience must equal resource_url plus mcp_path ({advertised}), because that is the resource clients request a token for. "
            "Omit audience to use it."
        )
    return advertised


def resource_at(resource_url: str, mcp_path: str | None) -> str:
    """Return the resource FastMCP advertises for a path, built through AnyHttpUrl so host case, default ports and escaping match."""
    base = str(AnyHttpUrl(resource_url))
    if not mcp_path:
        return base
    return str(AnyHttpUrl(f"{base.rstrip('/')}/{mcp_path.lstrip('/')}"))


def require_mounted_at_audience(provider: Auth0MCPProvider, resource_url: str, audience: str) -> None:
    """Make FastMCP fail at startup when the path it serves gives a resource other than the audience."""
    set_mcp_path = provider.set_mcp_path

    def checked(mcp_path: str | None) -> None:
        set_mcp_path(mcp_path)
        resource = resource_at(resource_url, mcp_path)
        if resource != audience:
            raise ConfigurationError(
                f"FastMCP serves the MCP endpoint at a path that advertises {resource}, but the audience is {audience}. "
                "Set mcp_path to the path passed to http_app or run."
            )

    provider.set_mcp_path = checked
