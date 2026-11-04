"""Token verification for FastMCP, backed by the auth0-ai-mcp client."""

from __future__ import annotations

import logging

from auth0_ai_mcp import (
    AuthServerUnavailableError,
    McpServerClient,
    VerifyAccessTokenError,
    build_principal,
)
from fastmcp.server.auth.auth import AccessToken, TokenVerifier

logger = logging.getLogger(__name__)


class Auth0TokenVerifier(TokenVerifier):
    """FastMCP token verifier that validates Auth0 access tokens.

    The returned `AccessToken` carries the verified claims so the middleware can build the
    caller without verifying the token again.

    Args:
        mcp_client: The client that verifies the token, including the organization policy.
        required_scopes: Scopes every request must carry. FastMCP rejects requests without them.
    """

    def __init__(self, mcp_client: McpServerClient, required_scopes: list[str] | None = None) -> None:
        super().__init__(required_scopes=required_scopes)
        self._client = mcp_client

    async def verify_token(self, token: str) -> AccessToken | None:
        """Verify a bearer token.

        Args:
            token: The raw access token from the `Authorization` header.

        Returns:
            The verified `AccessToken`, or None if the token is blank, invalid or lacks the
            claims needed to identify the caller.

        Raises:
            AuthServerUnavailableError: If Auth0 cannot be reached to verify the token.
        """
        if not token.strip():
            return None
        try:
            verified = await self._client.verify_access_token(token)
            principal = build_principal(verified.claims)
        except AuthServerUnavailableError:
            raise
        except VerifyAccessTokenError as exc:
            logger.warning("Token rejected: %s: %r", type(exc).__name__, str(exc))
            return None
        return AccessToken(
            token=token,
            client_id=principal.client_id,
            scopes=list(principal.scopes),
            expires_at=int(principal.expires_at),
            subject=principal.sub,
            claims=verified.claims,
        )
