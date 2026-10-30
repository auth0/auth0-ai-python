# Examples

This page walks through a complete Auth0-secured MCP server using the ASGI adapter shipped with `auth0-ai-mcp`. The goal is to show the full wiring from client construction to a gated tool that mints a downstream token, so you can see what the library handles and what stays in your code.

- [Building the client](#building-the-client)
- [Wiring the ASGI adapter](#wiring-the-asgi-adapter)
- [Writing a gated tool](#writing-a-gated-tool)
- [Complete example - b2b_ecommerce](#complete-example---b2b_ecommerce)

## Building the client

```python
from auth0_ai_mcp import create_mcp_client

client = create_mcp_client(
    domain="your-tenant.auth0.com",
    audience="https://your-mcp-server/mcp",
    client_id="YOUR_CLIENT_ID",
    client_secret="YOUR_CLIENT_SECRET",
)
```

Every client option is described in [Configuration](./docs/Configuration.md).

## Wiring the ASGI adapter

```python
from mcp.server.mcpserver import MCPServer
from auth0_ai_mcp.middleware import Auth0AsgiMiddleware

mcp = MCPServer(name="My Server")

secured_app = Auth0AsgiMiddleware(
    mcp.streamable_http_app(),
    mcp_client=client,
    scopes_supported=["read:weather"],
    resource_name="My Server",
    resource_documentation="https://your-mcp-server/docs",
)
```

From this point on, the library verifies every incoming token, rejects bad ones with a `401` before any tool runs, and serves the protected resource metadata. See [Token Verification](./docs/TokenVerification.md) and [Configuration](./docs/Configuration.md).

## Writing a gated tool

```python
from auth0_ai_mcp import require_caller_mcp_client, with_required_scopes

@with_required_scopes("read:weather")
async def get_weather(location: str) -> dict:
    auth0 = require_caller_mcp_client()
    token = await auth0.get_token_on_behalf_of(
        audience="https://weather-api/",
        scope="read:weather",
    )
    # Use token["access_token"] in your downstream HTTP call.
    ...
```

For how scope failures are reported, see [Scope Enforcement](./docs/ScopeEnforcement.md#errors).

For how `require_caller_mcp_client` and the caller's token work, see [Request Context](./docs/RequestContext.md#requestscopedmcpclient).

## Complete example - b2b_ecommerce

The [`examples/b2b_ecommerce`](./examples/b2b_ecommerce/) directory contains a runnable server whose flagship `cancel_and_refund_order` tool touches two downstream services (orders and payments) in one call, minting a separate scoped token for each via On-Behalf-Of. It also shows:

- An in-memory `token_store` passed to `create_mcp_client` for caching OBO tokens, and `scope_matching` driven by an environment variable to switch between matching modes at deploy time. See [Token Caching](./docs/TokenCaching.md) for what a production store needs and the available modes.
- Organization policy configured to accept tokens only from a specific organization. The policy is optional and defaults to `"allow"`. See [Organization Policy](./docs/OrganizationPolicy.md).
