# On-Behalf-Of Token Exchange

The On-Behalf-Of (OBO) exchange trades the caller's incoming token for a narrower token scoped to a specific downstream API, so a tool can call that API as the user without ever forwarding the user's original token.

The exchange uses RFC 8693 through `auth0-api-python`. Auth0 is the authority on which downstream audiences a given client may exchange for, so the audience you pass must be one Auth0 is configured to issue tokens for. The `client_id` and `client_secret` options this needs are described in [Configuration](./Configuration.md).

## Calling the exchange inside a tool

Inside a tool, get the request-scoped client with `require_caller_mcp_client()` and call `get_token_on_behalf_of` on it:

```python
from auth0_ai_mcp import require_caller_mcp_client, with_required_scopes

@with_required_scopes("read:weather")
async def get_weather(location: str) -> dict:
    auth0 = require_caller_mcp_client()
    token = await auth0.get_token_on_behalf_of(audience="https://weather-api/", scope="read:weather")
    # call the downstream API with token["access_token"]
```

The full signature is:

```python
RequestScopedMcpClient.get_token_on_behalf_of(*, audience: str, scope: str | None = None) -> TokenSet
```

The returned `TokenSet` carries `access_token` and `expires_at`, plus `granted_scopes` when the token response carried a `scope`. Pass `token["access_token"]` to the downstream HTTP call.

For how to read the caller and the request-scoped client, see [RequestContext.md](RequestContext.md).

## Downscope protection

If the exchanged token comes back with fewer scopes than were requested, `get_token_on_behalf_of` raises `DownscopedTokenError`, so tool code never receives a token that is missing scopes it asked for.

The token store still caches the exchanged token under the scopes it was actually granted. See [Scope re-check on every hit](./TokenCaching.md#scope-re-check-on-every-hit).

The check only runs when the token response carries a `scope` field. An absent `scope` field means the grant matched the request, which is the normal case per RFC 6749 section 5.1, so nothing is rejected in that case.

Client credentials runs the same check (see below). Token Vault does not, because its scopes are set on the connection (see [TokenVault.md](TokenVault.md)).

## Expired results

If the exchanged token comes back already expired, `get_token_on_behalf_of` raises `GetTokenByExchangeProfileError`.

## Caching

By default there is no cache and every call to `get_token_on_behalf_of` performs a fresh exchange. To add a cache in front of the exchange, pass a `token_store` to `create_mcp_client`. See [TokenCaching.md](TokenCaching.md) for the store interface, cache-key details, and scope-matching modes.

## Server-identity calls (client credentials)

Some tools need to act as the server itself rather than on behalf of a specific user. For those, `get_client_credentials_token(*, audience, scope=None)` on either `McpServerClient` or `RequestScopedMcpClient` requests a token for the server itself using the configured `client_id` and `client_secret`.

```python
token = await auth0.get_client_credentials_token(audience="https://internal-api/", scope="run:jobs")
# use token["access_token"]
```

The result has the same `TokenSet` shape, including `granted_scopes`. It runs the same downscope check and raises `DownscopedTokenError`, and it raises `GetClientCredentialsTokenError` when the token is already expired.
