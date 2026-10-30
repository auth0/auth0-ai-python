"""A client bound to one request's token.

Tool code calls `get_token_on_behalf_of` on this without ever handling the raw
incoming token. The token is closed over here, so a tool cannot accidentally forward
or leak it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .principal import Principal

if TYPE_CHECKING:
    from auth0_api_python import TokenSet, VerifiedToken

    from .client import McpServerClient


class RequestScopedMcpClient:
    """Wraps the shared server client with this request's verified token and principal."""

    def __init__(self, client: McpServerClient, verified: VerifiedToken, principal: Principal):
        self._client = client
        self._verified = verified
        self._principal = principal

    async def get_token_on_behalf_of(self, *, audience: str, scope: str | None = None) -> TokenSet:
        """Exchange the caller's token for a downstream token for `audience`."""
        return await self._client.get_token_on_behalf_of(
            self._verified, audience=audience, scope=scope
        )

    async def get_client_credentials_token(
        self, *, audience: str, scope: str | None = None
    ) -> TokenSet:
        """Obtain a client credentials token for a server-to-server call."""
        return await self._client.get_client_credentials_token(audience=audience, scope=scope)

    async def get_token_for_connection(
        self, *, connection: str, login_hint: str | None = None
    ) -> TokenSet:
        """Exchange the caller's token for a federated provider token via Token Vault."""
        return await self._client.get_token_for_connection(
            self._verified, connection=connection, login_hint=login_hint
        )

    def get_principal(self) -> Principal:
        """Return the verified caller for this request."""
        return self._principal
