# Writing an Adapter

An adapter's whole job is to verify the incoming token, put the caller into the request context before the MCP handler runs, and serve the protected-resource metadata.

`auth0-ai-mcp` is framework-agnostic, so any MCP framework can be wired up using the same four-step pattern. Most users will not need to write one from scratch because the package ships a ready-made ASGI middleware.

The snippets use the 2.x import `mcp.server.mcpserver`. The `mcp` extra requires 2.2 or later, and the tool error text described in these guides was checked on 2.3.

## Ready-made integrations

**ASGI (Starlette, FastAPI, official MCP app).** Import `Auth0AsgiMiddleware` from `auth0_ai_mcp.middleware`:

```python
from auth0_ai_mcp import create_mcp_client
from auth0_ai_mcp.middleware import Auth0AsgiMiddleware

mcp_client = create_mcp_client(DOMAIN, AUDIENCE, client_id="...", client_secret="...")
app = Auth0AsgiMiddleware(
    mcp.streamable_http_app(host="127.0.0.1"),
    mcp_client=mcp_client,
)
```

> [!WARNING]
> The MCP SDK checks the Host and Origin headers when `streamable_http_app(host=...)` is `127.0.0.1`, `localhost` or `::1`, which is also the default. Any other value, such as `"0.0.0.0"`, turns the checks off.

For a public URL, keep the checks on and list your host. Without this every request to a public host gets a `421`. A request with an `Origin` header that is not in `allowed_origins` gets a `403`, so list the origins of any browser client there.

```python
from mcp.server.transport_security import TransportSecuritySettings

app = Auth0AsgiMiddleware(
    mcp.streamable_http_app(
        transport_security=TransportSecuritySettings(allowed_hosts=["your-mcp-server", "your-mcp-server:*"]),
    ),
    mcp_client=mcp_client,
)
```

**Prefect FastMCP.** Use the `auth0-ai-fastmcp` package. FastMCP users do not need to hand-write an adapter.

## Writing an adapter for another framework

If neither built-in option covers your framework, follow these four steps.

### 1. Pull and validate the bearer token

Read the `Authorization` header. If the token is missing or blank, or the scheme is not `Bearer`, respond `401` and stop. The challenge should carry `resource_metadata` and no `error`, and `scope` if you advertise scopes. Build the header with `build_www_authenticate(resource_metadata_url, scope=...)` from `auth0_ai_mcp.middleware`. The request must never reach a tool handler without a verified token.

### 2. Verify the token and get the caller

```python
from auth0_ai_mcp import build_principal

verified = await mcp_client.verify_access_token(token)
principal = build_principal(verified.claims)
```

A failed verification raises `VerifyAccessTokenError`, and `build_principal` raises it too for claims it rejects. Catch it, log the real reason, and return a `401` built with `build_www_authenticate(resource_metadata_url, "invalid_token", "The access token is not valid")`. The real reason is not echoed to the client. `AuthServerUnavailableError` is a subclass that means Auth0 could not be reached, so catch it first and return a `503` without a challenge. `DomainsResolverError` is not a `VerifyAccessTokenError`, so catch it separately and return the same `503`. A `401` would make the client log in again for no reason.

### 3. Build and set the request context

```python
from auth0_ai_mcp import RequestContext, bind_request_context

context = RequestContext(
    principal=principal,
    mcp_client=mcp_client.with_token(verified, principal),
)
with bind_request_context(context):
    # run the MCP handler
    ...
```

`bind_request_context` sets the context for the handler and always resets it, even when the handler raises.

### 4. Serve the protected-resource metadata

Serve `/.well-known/oauth-protected-resource` per RFC 9728. Use the helper to build the document:

```python
from auth0_ai_mcp.middleware import build_protected_resource_metadata

metadata = build_protected_resource_metadata(mcp_client)
```

Return the result as JSON with a `200` status.

The helper reads the resource from `mcp_client.audience` and the authorization server from `mcp_client.domain`. Its options (`resource_url`, `authorization_servers`, `scopes_supported`, `resource_name` and `resource_documentation`) are described under `Auth0AsgiMiddleware` in [Configuration](./Configuration.md#auth0asgimiddleware).

Serve it at `/.well-known/oauth-protected-resource` and also at that path followed by the path of the resource. For a resource of `https://host/mcp` that is `/.well-known/oauth-protected-resource/mcp`. RFC 9728 puts the well-known segment between the host and the path, so clients look for the path-suffixed URL first. Use the path-suffixed URL as the `resource_metadata` value in every `401` challenge.

## What tool code sees

Once the context is set, tool code uses `get_caller_principal()`, `require_caller_mcp_client()`, and `with_required_scopes(...)` the same way regardless of which adapter wired them up. See [RequestContext.md](RequestContext.md) for reading the caller and [ScopeEnforcement.md](ScopeEnforcement.md) for protecting tools with required scopes.
