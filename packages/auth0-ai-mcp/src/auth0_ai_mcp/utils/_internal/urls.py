from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from auth0_api_python.errors import ConfigurationError
from auth0_api_python.utils import normalize_domain

if TYPE_CHECKING:
    from ...client import McpServerClient


def resolve_resource_url(mcp_client: McpServerClient, resource_url: str | None) -> str:
    """Return the advertised resource URL, defaulting to the client audience, which tokens must carry as `aud`."""
    audience = mcp_client.audience
    if resource_url is None:
        resource_url = audience
    elif resource_url != audience:
        raise ConfigurationError(
            "resource_url must equal the client audience, because tokens for any other audience are rejected. "
            "Omit resource_url to use the audience."
        )
    if not is_plain_url(resource_url, ("http", "https")):
        raise ConfigurationError(
            "resource_url (the client audience unless set) must be an absolute http or https URL with a host and no fragment, credentials or whitespace"
        )
    return resource_url


def resolve_authorization_servers(
    mcp_client: McpServerClient, authorization_servers: list[str] | None
) -> list[str]:
    """Return the advertised issuers, defaulting to the client's tenant domain."""
    if authorization_servers is None:
        domain = mcp_client.domain
        if not domain:
            raise ConfigurationError(
                "authorization_servers is required when the client has no single domain"
            )
        try:
            issuer = normalize_domain(domain)
        except ValueError as exc:
            raise ConfigurationError(f"domain is not a valid tenant domain: {exc}") from exc
        # The core builds its discovery URL from the raw domain, so anything normalize_domain trims would break verification.
        if issuer != f"https://{domain.lower()}/" or any(ch.isspace() for ch in issuer):
            raise ConfigurationError("domain must be a bare host such as tenant.auth0.com, with no scheme, path or whitespace")
        return [issuer]
    if not isinstance(authorization_servers, list) or not authorization_servers:
        raise ConfigurationError("authorization_servers must be a non-empty list of https URLs")
    for server in authorization_servers:
        if not is_plain_url(server, ("https",)) or urlsplit(server).query:
            raise ConfigurationError(
                "authorization_servers must hold absolute https URLs with a host and no query, fragment, credentials or whitespace"
            )
    return authorization_servers


def is_plain_url(value: object, schemes: tuple[str, ...]) -> bool:
    """True for an absolute URL of one of `schemes` with a host and no fragment, credentials or whitespace."""
    if not isinstance(value, str) or any(ch.isspace() or not ch.isprintable() for ch in value):
        return False
    parts = urlsplit(value)
    return parts.scheme in schemes and bool(parts.hostname) and not parts.fragment and parts.username is None and parts.password is None


def resource_path(path: str) -> str:
    """The resource URL's path for RFC 9728 path insertion, empty when the path is only "/"."""
    return "" if path == "/" else path
