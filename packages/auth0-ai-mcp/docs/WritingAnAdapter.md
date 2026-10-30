# Writing an Adapter

An adapter's whole job is to verify the incoming token, put the caller into the request context before the MCP handler runs, and serve the protected-resource metadata.

`auth0-ai-mcp` is framework-agnostic, so any MCP framework can be wired up using the same four-step pattern. Most users will not need to write one from scratch because the package ships a ready-made ASGI middleware.

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
> The MCP SDK turns on its Host and Origin checks only when the app is bound to localhost, so keep `127.0.0.1` for local use. Bind another interface only behind a trusted proxy or after configuring the allowed hosts.

**Prefect FastMCP.** Use the `auth0-ai-fastmcp` package. FastMCP users do not need to hand-write an adapter.

## Writing an adapter for another framework

If neither built-in option covers your framework, follow these four steps.

### 1. Pull and validate the bearer token

Read the `Authorization` header. If the token is missing or blank, or the scheme is not `Bearer`, respond `401` and stop. The challenge should carry `resource_metadata` and no `error`. Build the header with `build_www_authenticate(resource_metadata_url)` from `auth0_ai_mcp.middleware`. The request must never reach a tool handler without a verified token.

### 2. Verify the token and get the caller

```python
from auth0_ai_mcp import build_principal

verified = await mcp_client.verify_access_token(token)
principal = build_principal(verified.claims)
```

A failed verification raises `VerifyAccessTokenError`, and `build_principal` raises it too for claims it rejects. Catch it, log the real reason, and return a `401` built with `build_www_authenticate(resource_metadata_url, "invalid_token", "The access token is not valid")`. The real reason is not echoed to the client. `AuthServerUnavailableError` is a subclass that means Auth0 could not be reached, so catch it first and return a `503` without a challenge. A `401` would make the client log in again for no reason.

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
