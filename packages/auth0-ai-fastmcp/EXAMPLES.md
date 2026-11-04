# Examples

This page walks through building a complete Auth0-secured FastMCP server using `Auth0FastMCP`.

## Full server example

The example below shows every piece you need: configuring `Auth0FastMCP`, registering the provider and middleware, advertising tool scopes, and gating a tool that mints a downstream token on behalf of the caller.

```python
from fastmcp import FastMCP
from auth0_ai_fastmcp import (
    Auth0FastMCP,
    Auth0FastMCPOptions,
    require_scopes,
    with_required_scopes,
)
from auth0_ai_mcp import get_caller_principal, require_caller_mcp_client

# The provider fetches the tenant's OIDC configuration at startup.
auth0 = Auth0FastMCP(Auth0FastMCPOptions(
    domain="your-tenant.auth0.com",
    resource_url="https://your-api.example.com",
    tool_scopes=["tool:read_orders", "tool:place_order"],
    client_id="YOUR_CLIENT_ID",
    client_secret="YOUR_CLIENT_SECRET",
))

mcp = FastMCP(name="My Store Server", auth=auth0.provider)
mcp.add_middleware(auth0.middleware)


@mcp.tool
@with_required_scopes("tool:read_orders")
async def read_orders() -> list[dict]:
    """Return the caller's orders from the downstream API."""
    client = require_caller_mcp_client()
    token = await client.get_token_on_behalf_of(
        audience="https://store-api/",
        scope="read:orders",
    )
    # Use token["access_token"] to call the downstream API.
    ...


@mcp.tool
@with_required_scopes("tool:place_order")
async def place_order(item_id: str, quantity: int) -> dict:
    """Place an order on behalf of the caller."""
    client = require_caller_mcp_client()
    token = await client.get_token_on_behalf_of(
        audience="https://store-api/",
        scope="write:orders",
    )
    # Use token["access_token"] to call the downstream API.
    ...
```

For what each `Auth0FastMCPOptions` field does, see [Configuration](./docs/Configuration.md#auth0fastmcpoptions-fields).

## Resources and prompts

The middleware sets the caller for resources and prompts too. Check the scope with `require_scopes` inside the handler, or put `with_required_scopes` on the handler as it is on a tool.

```python
@mcp.resource("orders://recent")
async def recent_orders() -> str:
    require_scopes(get_caller_principal(), "resource:recent_orders")
    return "..."


@mcp.prompt
async def order_summary() -> str:
    require_scopes(get_caller_principal(), "prompt:order_summary")
    return "Summarize the caller's recent orders."
```

## Runnable version

A complete runnable server using this pattern lives in [`examples/b2b_ecommerce`](./examples/b2b_ecommerce/).
