from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ...principal import Principal

try:
    from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
    from mcp.server.auth.provider import AccessToken
except ImportError:  # Without mcp there is no session manager to bind, so scope["user"] is skipped.
    AuthenticatedUser = None
    AccessToken = None

# Tool code can reach scope["user"], so the raw bearer token never goes there.
_REDACTED_VALUE = "redacted"


def access_token_info(principal: Principal, claims: Mapping[str, Any]) -> AccessToken:
    """Describe the caller to the mcp session manager, which keys a session on client, issuer and subject."""
    issuer = claims.get("iss")
    return AccessToken(
        token=_REDACTED_VALUE,
        client_id=principal.client_id,
        scopes=principal.scopes,
        expires_at=int(principal.expires_at),
        subject=principal.sub,
        claims={"iss": issuer} if isinstance(issuer, str) else None,
    )
