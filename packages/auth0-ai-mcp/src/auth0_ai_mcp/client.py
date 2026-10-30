"""The server client: verify incoming tokens and exchange them for downstream tokens.

This sits beside auth0-api-python. It owns no MCP framework and registers no tools.
It verifies the bearer token, delegates the OBO exchange to the core SDK (which handles
caching when a token_store is wired in via create_mcp_client), and hands tool code a
request-scoped client. Each framework adapter wires this into a request pipeline.
"""

from __future__ import annotations

from typing import Literal

from auth0_api_python import (
    AbstractTokenStore,
    ApiClient,
    ApiClientOptions,
    GetAccessTokenForConnectionError,
    GetClientCredentialsTokenError,
    TokenSet,
    VerifiedToken,
)
from auth0_api_python.errors import (
    ConfigurationError,
    GetTokenByExchangeProfileError,
)

from .principal import Principal
from .request_scoped_client import RequestScopedMcpClient
from .utils._internal import exchange, telemetry


class McpServerClient:
    """Verifies incoming tokens and exchanges them for downstream API tokens."""

    def __init__(
        self,
        api_client: ApiClient,
    ):
        self._api = api_client

    @property
    def domain(self) -> str | None:
        """The tenant domain the core client was configured with, or None in multi-domain mode."""
        return self._api.options.domain

    @property
    def audience(self) -> str:
        """The API identifier the core client expects in incoming tokens."""
        return self._api.options.audience

    def with_token(self, verified: VerifiedToken, principal: Principal) -> RequestScopedMcpClient:
        """Bind this client to one request's verified token and principal."""
        return RequestScopedMcpClient(self, verified, principal)

    async def verify_access_token(self, access_token: str) -> VerifiedToken:
        """Verify the incoming token, returning it paired with its verified claims."""
        claims = await self._api.verify_access_token(access_token=access_token)
        return VerifiedToken(access_token=access_token, claims=claims)

    async def get_token_on_behalf_of(
        self,
        verified: VerifiedToken,
        *,
        audience: str,
        scope: str | None = None,
    ) -> TokenSet:
        """Exchange the caller's token for a downstream token for the given audience and scope.

        Raises:
            DownscopedTokenError: If the exchange grants fewer scopes than were requested.
            GetTokenByExchangeProfileError: If the exchanged token is already expired.
        """
        result = await self._api.get_token_on_behalf_of(
            verified.access_token, audience, scope, verified=verified
        )
        exchange.reject_if_downscoped(scope, result)
        exchange.reject_if_expired(result, GetTokenByExchangeProfileError)
        return exchange.token_set(result)

    async def get_client_credentials_token(
        self, *, audience: str, scope: str | None = None
    ) -> TokenSet:
        """Obtain a client credentials token for a server-to-server call.

        Args:
            audience: Target API identifier.
            scope: Optional space-separated scopes to request.

        Raises:
            GetClientCredentialsTokenError: If client credentials are not configured, the token endpoint is unreachable, or the returned token is already expired.
            ApiError: If the token endpoint returns an error.
            DownscopedTokenError: If the token endpoint grants fewer scopes than were requested.
        """
        result = await self._api.get_client_credentials_token(audience=audience, scope=scope)
        exchange.reject_if_downscoped(scope, result)
        exchange.reject_if_expired(result, GetClientCredentialsTokenError)
        return exchange.token_set(result)

    async def get_token_for_connection(
        self,
        verified: VerifiedToken,
        *,
        connection: str,
        login_hint: str | None = None,
    ) -> TokenSet:
        """Exchange the caller's token for a federated provider token via Token Vault.

        Args:
            verified: The verified incoming token for the requesting user.
            connection: The Auth0 federated connection identifier (e.g. "google-oauth2").
            login_hint: Optional email to pre-fill the federated login prompt.

        Raises:
            GetAccessTokenForConnectionError: If client credentials are not configured, the exchange fails, or the returned token is already expired.
            ApiError: If the token exchange endpoint returns an error.
        """
        options: dict = {
            "connection": connection,
            "access_token": verified.access_token,
            **({"login_hint": login_hint} if login_hint else {}),
        }
        result = await self._api.get_access_token_for_connection(options, verified=verified)
        exchange.reject_if_expired(result, GetAccessTokenForConnectionError)
        return exchange.token_set(result)


def create_mcp_client(
    domain: str | None = None,
    audience: str | None = None,
    *,
    client_id: str | None = None,
    client_secret: str | None = None,
    token_store: AbstractTokenStore | None = None,
    scope_matching: Literal["strict", "non_strict"] = "strict",
    organization_policy: Literal["required", "allow"] = "allow",
    organization_id: str | list[str] | None = None,
    client_info: dict | None = None,
    api_client: ApiClient | None = None,
) -> McpServerClient:
    """Build an McpServerClient.

    Args:
        domain: The Auth0 tenant domain, for example "tenant.auth0.com". Required unless `api_client` is passed.
        audience: The API identifier the incoming tokens are issued for. Required unless `api_client` is passed.
        client_id: Needed for the on-behalf-of exchange, client credentials tokens and Token Vault. Token verification works without it.
        client_secret: Needed alongside `client_id` for the same flows.
        token_store: Optional store for the core SDK's token cache.
        scope_matching: Cache scope-matching mode, "strict" or "non_strict". "non_strict" needs an `IndexedTokenStore`.
        organization_policy: "required" rejects tokens without an `org_id` claim, "allow" accepts them.
        organization_id: The Organization ID or IDs a token must carry. Only valid with `organization_policy="required"`.
        client_info: Identifies a package built on this one in the Auth0-Client header. A dict with non-empty string "name" and "version" keys and an optional "env" dict of string keys and values.
        api_client: A prebuilt core client to use as is. Pass it instead of the options above, including `domain` and `audience`.

    Returns:
        The server client.

    Raises:
        ConfigurationError: If `domain` or `audience` is missing without `api_client`, or if `api_client` is passed together with any of `domain`, `audience`, `client_id`, `client_secret`, `token_store`, `scope_matching`, `organization_policy`, `organization_id` or `client_info`, or if `client_info` does not have the shape described above.
    """
    if api_client is None:
        if domain is None or audience is None:
            raise ConfigurationError("domain and audience are required unless api_client is passed")
        api_client = ApiClient(
            ApiClientOptions(
                domain=domain,
                audience=audience,
                client_id=client_id,
                client_secret=client_secret,
                token_store=token_store,
                scope_matching=scope_matching,
                organization_policy=organization_policy,
                organization_id=organization_id,
                client_info=telemetry.build_client_info(client_info),
            )
        )
    elif (
        domain is not None
        or audience is not None
        or client_id is not None
        or client_secret is not None
        or token_store is not None
        or scope_matching != "strict"
        or organization_policy != "allow"
        or organization_id is not None
        or client_info is not None
    ):
        raise ConfigurationError("api_client cannot be combined with other client options, because they would be ignored")
    return McpServerClient(api_client)
