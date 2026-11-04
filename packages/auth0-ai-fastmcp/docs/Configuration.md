# Configuration

Everything is set on `Auth0FastMCPOptions`, which you pass once to `Auth0FastMCP(options)` at startup. The `Auth0FastMCP` object then hands back a provider and a middleware for you to mount on your FastMCP server.

```python
from fastmcp import FastMCP
from auth0_ai_fastmcp import Auth0FastMCP, Auth0FastMCPOptions

auth0 = Auth0FastMCP(
    Auth0FastMCPOptions(
        domain="your-tenant.auth0.com",
        resource_url="https://your-api.example.com",
        tool_scopes=["tool:read_orders"],
    )
)

mcp = FastMCP(name="My MCP Server", auth=auth0.provider)
mcp.add_middleware(auth0.middleware)
```

Settings are checked when `Auth0FastMCP(options)` runs, so a bad combination fails at server startup rather than on the first request.

## Auth0FastMCPOptions fields

- `domain` (str) - Auth0 tenant domain as a bare host with no scheme, path, query or whitespace, for example `"your-tenant.auth0.com"`. An empty value, or one with a scheme, a path, a query, `#`, `@` or whitespace, raises `ConfigurationError`. The OIDC discovery document is fetched when `Auth0FastMCP` is created, so an unreachable domain fails there with a connection error.
- `resource_url` (str) - base URL of this server without the MCP path. See [resource_url and audience](#resource_url-and-audience).
- `audience` (str | None, default `None`) - this server's API identifier in Auth0, which incoming tokens are validated against. Defaults to `resource_url` plus `mcp_path` and must equal it when set. See [resource_url and audience](#resource_url-and-audience).
- `mcp_path` (str, default `"/mcp"`) - path the MCP endpoint is mounted at. See [resource_url and audience](#resource_url-and-audience).
- `tool_scopes` (list[str], default `[]`) - scopes advertised so the MCP client requests them at login. See [Tool Scopes](./ToolScopes.md).
- `client_id` (str | None, default `None`) - client id for token exchanges, needed only when tools call `get_token_on_behalf_of`, `get_client_credentials_token` or `get_token_for_connection`.
- `client_secret` (str | None, default `None`) - client secret for the same exchanges.
- `token_store` (AbstractTokenStore | None, default `None`) - backing store for cached OBO tokens. See [Scope matching for cached OBO tokens](#scope-matching-for-cached-obo-tokens).
- `scope_matching` (str, default `"strict"`) - how cached OBO tokens are matched to the scopes a tool asks for, either `"strict"` or `"non_strict"`. See [Scope matching for cached OBO tokens](#scope-matching-for-cached-obo-tokens).
- `organization_policy` (str, default `"allow"`) - whether tokens must carry an organization, either `"allow"` or `"required"`. See [Organization policy](#organization-policy).
- `organization_id` (str | list[str] | None, default `None`) - the organization or organizations accepted when the policy is `"required"`. See [Organization policy](#organization-policy).
- `required_scopes` (list[str] | None, default `None`) - scopes every token must carry. A token missing any of them is rejected with a `403` and `insufficient_scope` before any handler runs. See [Required scopes](#required-scopes), and [Tool Scopes](./ToolScopes.md) for how they are advertised.

## resource_url and audience

`resource_url` is the base URL of your server with no MCP path on the end. FastMCP adds the path the MCP endpoint is mounted at (`/mcp` by default) and advertises the result as the resource in the protected-resource metadata.

The MCP client reads that advertised resource and asks Auth0 for a token for it, so the audience that incoming tokens are validated against has to be the same value. It defaults to `resource_url` plus `mcp_path`, which means `resource_url="https://your-api.example.com"` gives the audience `https://your-api.example.com/mcp`. That value is also the API identifier to register in Auth0.

Set `mcp_path` if the server is mounted somewhere other than `/mcp`, and pass the same path to FastMCP. You can set `audience` yourself, but it must equal `resource_url` plus `mcp_path`. Any other value raises `ConfigurationError` at startup, because tokens minted for it would never match the advertised resource. If the path given to `http_app` or `run` differs from `mcp_path`, building the app raises the same error.

> [!WARNING]
> Do not add `/mcp` to the end of `resource_url`. FastMCP would then advertise `https://your-api.example.com/mcp/mcp`, so the audience becomes that value too and no longer matches the API you registered in Auth0. The client never gets a token the server accepts, and every request gets a `401`.

## Organization policy

`organization_policy` is `"allow"` (the default) or `"required"`, and `organization_id` is a single string or a list of strings accepted when the policy is `"required"`. For what each policy accepts, see [Organization Policy](https://github.com/auth0/auth0-ai-python/blob/main/packages/auth0-ai-mcp/docs/OrganizationPolicy.md).

`organization_id` only works with `organization_policy="required"`. Setting it while the policy is `"allow"` raises `ConfigurationError` at startup, and so does an empty string or an empty list.

```python
Auth0FastMCPOptions(
    domain="your-tenant.auth0.com",
    resource_url="https://your-api.example.com",
    tool_scopes=["tool:read_orders"],
    organization_policy="required",
    organization_id="org_abc",
)
```

The check runs inside `Auth0TokenVerifier`, before any tool, resource or prompt runs. A rejected token gets a `401` with `invalid_token` from FastMCP, the same as any other bad token, so when every request fails in org mode, check the `org_id` in the token first.

Auth0 copies `org_id` from the user's token into every token from `get_token_on_behalf_of` on its own, so tool code passes nothing extra. For the tenant setting the On-Behalf-Of client needs in organization mode, see [Organization Policy](https://github.com/auth0/auth0-ai-python/blob/main/packages/auth0-ai-mcp/docs/OrganizationPolicy.md). For the example tenant setup, see [Running in B2B org mode](../examples/b2b_ecommerce/README.md#running-in-b2b-org-mode).

## Scope matching for cached OBO tokens

Caching is off unless you set `token_store`, along with `client_id` and `client_secret` for the On-Behalf-Of exchange. Without a store, every `get_token_on_behalf_of` call does a fresh exchange with Auth0.

`scope_matching` is `"strict"` (the default) or `"non_strict"` and decides when a saved token is reused. For how each mode matches tokens, see [Scope-matching modes](https://github.com/auth0/auth0-ai-python/blob/main/packages/auth0-ai-mcp/docs/TokenCaching.md#scope-matching-modes), and for how saved tokens are keyed, see [Cache key](https://github.com/auth0/auth0-ai-python/blob/main/packages/auth0-ai-mcp/docs/TokenCaching.md#cache-key).

`"non_strict"` needs a `token_store` that subclasses `IndexedTokenStore`. A plain store, or no `token_store` at all, raises `ConfigurationError` at startup.

> [!WARNING]
> With `non_strict`, a tool can get a token with more access than it asked for. A tool that asks for `read:inventory` can be handed a saved token that also carries `write:inventory`. Only choose it when that is acceptable for every tool on the server.

```python
store = YourIndexedTokenStore(secret="YOUR_STORE_SECRET")  # your IndexedTokenStore subclass

Auth0FastMCPOptions(
    domain="your-tenant.auth0.com",
    resource_url="https://your-api.example.com",
    tool_scopes=["tool:read_orders"],
    client_id="YOUR_OBO_CLIENT_ID",
    client_secret="YOUR_OBO_CLIENT_SECRET",
    token_store=store,
    scope_matching="non_strict",
)
```

See [Token Caching](https://github.com/auth0/auth0-ai-python/blob/main/packages/auth0-ai-mcp/docs/TokenCaching.md) for the store interface, expiry and the index, and a [Redis store example](https://github.com/auth0/auth0-ai-python/blob/main/packages/auth0-ai-mcp/docs/TokenCaching.md#a-redis-store).

## Required scopes

`required_scopes` applies to every request on the server, whatever the tool, resource or prompt. It is separate from `tool_scopes`, which only advertises scopes for the client to ask for at login. For how required scopes are advertised, see [Tool Scopes](./ToolScopes.md). For which token claim scopes are read from, see [Scope Enforcement](https://github.com/auth0/auth0-ai-python/blob/main/packages/auth0-ai-mcp/docs/ScopeEnforcement.md).

- An invalid, expired or empty token is rejected by `Auth0TokenVerifier`, and FastMCP answers `401`.
- A valid token that lacks a required scope gets a `403` with `insufficient_scope`. The text names the missing scope (`Required scope: <scope>`) because the official `mcp` SDK writes it.
- If Auth0 cannot be reached to check a token, the verifier raises `AuthServerUnavailableError` instead of reporting the token as bad. The server answers `503` with `Retry-After: 5` and `Cache-Control: no-store` headers and no `WWW-Authenticate` challenge, so the client keeps its token and retries instead of logging in again. This applies to the provider from `Auth0FastMCP` only, a hand-wired provider answers with FastMCP's own `500`.

In every case the handler never runs.

This package does not check the `Host` or `Origin` header of a request. FastMCP has its own setting for that, `http_host_origin_protection`, which is off by default.

## What the middleware does

`Auth0ContextMiddleware` runs on every MCP request after the token is verified, including tool calls, resource reads, prompt requests and the list calls. It builds the caller's `Principal` from the verified token and makes it available to `get_caller_principal()` and `require_caller_mcp_client()` for the length of the request. The context is cleared when the request ends, even if the handler raises.

A request with no verified token raises `UnauthenticatedError`. With the provider mounted this does not happen, because FastMCP turns the request away first, so seeing it means the server was created without `auth=auth0.provider`. It is logged with a traceback so the missing provider is easy to spot. The `initialize` and `ping` requests are the exception, since they carry no caller. A token without a usable `sub`, `exp` or client id never counts as verified, so it gets a `401` before the middleware runs.

Tools should read the caller with `get_caller_principal()`. FastMCP's own `get_access_token()` still returns the raw bearer token, because the verifier hands it to FastMCP, so avoid it in tool code.

FastMCP runs middleware in the order it was added, so add `auth0.middleware` before any middleware of your own that reads the caller.

### Failed token exchanges

If a tool, resource or prompt lets an `ApiError` or a `DownscopedTokenError` escape, for example when Auth0 refuses an on-behalf-of or Token Vault exchange, the client gets `Token exchange failed (<error code>)`. One example is `Token exchange failed (federated_connection_refresh_token_not_found)`. The client never sees Auth0's own message, whether `mask_error_details` is on or off. The server log still has the full error and its traceback.

To tell the user something more useful, catch the error in the handler and raise your own `ToolError`, `ResourceError` or `PromptError`. The middleware leaves that message as it is.

```python
from auth0_ai_mcp import ApiError, require_caller_mcp_client
from fastmcp.exceptions import ToolError


@mcp.tool
async def calendar() -> str:
    client = require_caller_mcp_client()
    try:
        token = await client.get_token_for_connection(connection="google-oauth2")
    except ApiError as exc:
        if exc.code == "federated_connection_refresh_token_not_found":
            raise ToolError("Connect your Google account first") from exc
        raise
    ...
```

## Auth0FastMCP properties

After construction, `Auth0FastMCP` exposes three read-only properties.

- `.provider` - a FastMCP `Auth0MCPProvider`. Pass it as `FastMCP(auth=auth0.provider)`. It handles token verification and advertises the protected-resource metadata.
- `.middleware` - an `Auth0ContextMiddleware`. Register it with `mcp.add_middleware(auth0.middleware)`. It sets the request context so handler code can call `require_caller_mcp_client()` and `get_caller_principal()`. See [What the middleware does](#what-the-middleware-does).
- `.mcp_client` - the underlying `auth0-ai-mcp` `McpServerClient`, for advanced cases that need direct access to the core client.

`Auth0TokenVerifier` and `Auth0ContextMiddleware` are also exported directly from `auth0_ai_fastmcp`, for cases where you want to hand-wire the provider yourself instead of using `Auth0FastMCP`.
