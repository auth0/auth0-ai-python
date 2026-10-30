# Configuration

Two things are configured once at startup. `create_mcp_client` builds the client that verifies tokens and runs token exchanges, and `Auth0AsgiMiddleware` wraps your app with it.

## create_mcp_client

```python
from auth0_ai_mcp import create_mcp_client

client = create_mcp_client(
    domain="your-tenant.auth0.com",
    audience="https://your-mcp-server/mcp",
    client_id="YOUR_CLIENT_ID",
    client_secret="YOUR_CLIENT_SECRET",
)
```

- `domain` (str) - Auth0 tenant domain as a bare host such as `your-tenant.auth0.com`, with no scheme, path or whitespace. It must match the issuer of your tokens, so pass your custom domain here if you use one. Required unless `api_client` is passed.
- `audience` (str) - the API identifier incoming tokens are validated against. See [audience](#audience). Required unless `api_client` is passed.
- `client_id` (str | None, default `None`) - client id for token exchanges. Needed for [On-Behalf-Of](./OnBehalfOf.md), [client credentials](./OnBehalfOf.md#server-identity-calls-client-credentials) and [Token Vault](./TokenVault.md). Verifying incoming tokens works without it.
- `client_secret` (str | None, default `None`) - client secret for the same exchanges.
- `token_store` (AbstractTokenStore | None, default `None`) - backing store for cached tokens. See [Token Caching](./TokenCaching.md).
- `scope_matching` (str, default `"strict"`) - either `"strict"` or `"non_strict"`. See [Scope-matching modes](./TokenCaching.md#scope-matching-modes).
- `organization_policy` (str, default `"allow"`) - either `"allow"` or `"required"`. See [Organization Policy](./OrganizationPolicy.md).
- `organization_id` (str | list[str] | None, default `None`) - the organization or organizations accepted when the policy is `"required"`. See [Organization Policy](./OrganizationPolicy.md).
- `api_client` (ApiClient | None, default `None`) - a ready-made client to use as is. See [Passing a prebuilt client](#passing-a-prebuilt-client).

`scope_matching` and `organization_policy` only accept the values listed above.

### audience

> [!IMPORTANT]
> `audience` must be the public URL of your MCP server. It is also the API identifier you register in Auth0, so a token issued for any other value is rejected with a `401`.

### Passing a prebuilt client

`ApiClient` comes from [`auth0-api-python`](https://github.com/auth0/auth0-api-python), the library `auth0-ai-mcp` is built on. Build one yourself when you need an option `create_mcp_client` does not expose, such as multi-domain mode or DPoP settings.

```python
from auth0_api_python import ApiClient, ApiClientOptions
from auth0_ai_mcp import create_mcp_client

api_client = ApiClient(ApiClientOptions(
    domain="your-tenant.auth0.com",
    audience="https://your-mcp-server/mcp",
))
client = create_mcp_client(api_client=api_client)
```

Pass `api_client` and nothing else. Combining it with any other option raises `ConfigurationError`, because those options would be ignored.

## Auth0AsgiMiddleware

```python
from auth0_ai_mcp.middleware import Auth0AsgiMiddleware

secured_app = Auth0AsgiMiddleware(
    app,
    mcp_client=client,
    scopes_supported=["read:weather"],
    resource_name="My Server",
    resource_documentation="https://your-mcp-server/docs",
)
```

The middleware reads the resource from the client's `audience` and the authorization server from its `domain`, so neither is set twice.

- `app` - the ASGI app to protect.
- `mcp_client` - the client from `create_mcp_client`.
- `resource_url` (str | None, default `None`) - absolute http or https URL of the protected resource. Defaults to the client's `audience` and must equal it when given, otherwise `ConfigurationError` is raised.
- `authorization_servers` (list[str] | None, default `None`) - issuer URLs to advertise, each an absolute https URL. Defaults to the client's `domain`. Required when the client has no single `domain`, for example a prebuilt `api_client` in multi-domain mode.
- `scopes_supported` (list[str] | None, default `None`) - scopes to advertise, so the MCP client requests them at login.
- `resource_name` (str | None, default `None`) - human-readable name for the resource.
- `resource_documentation` (str | None, default `None`) - URL of documentation for the resource.

The last three are left out of the metadata document when you do not pass them. The document has no `jwks_uri`.

For where the metadata is served and what the middleware returns on a bad token, see [Token Verification](./TokenVerification.md#what-the-middleware-returns).

## Related

- [Token Verification](./TokenVerification.md) - what the middleware checks and returns.
- [Writing an Adapter](./WritingAnAdapter.md) - serving the metadata from another framework.
- [Token Caching](./TokenCaching.md) - `token_store` and `scope_matching`.
- [Organization Policy](./OrganizationPolicy.md) - `organization_policy` and `organization_id`.
