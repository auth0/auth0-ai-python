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
    tool_scopes=["tool:read_orders", "tool:place_order", "resource:recent_orders", "prompt:order_summary"],
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

The middleware sets the caller for resources and prompts too. Check the scope with `require_scopes` inside the handler, or put `with_required_scopes` on the handler as it is on a tool. The scopes used here are in `tool_scopes` in the full server above, so the MCP client requests them at login.

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

## Calling two downstream APIs from one tool

Ask once per downstream service, each with only its own scopes. See [On-Behalf-Of](https://github.com/auth0/auth0-ai-python/blob/main/packages/auth0-ai-mcp/docs/OnBehalfOf.md).

```python
@mcp.tool
@with_required_scopes("tool:cancel_order")
async def cancel_order(order_id: str) -> dict:
    client = require_caller_mcp_client()
    orders = await client.get_token_on_behalf_of(audience="https://orders.api/", scope="cancel:orders")
    payments = await client.get_token_on_behalf_of(audience="https://payments.api/", scope="write:refunds")
    # Call the orders API with orders["access_token"], then the payments API with payments["access_token"].
    ...
```

## Showing a useful message when an exchange fails

An `ApiError` or `DownscopedTokenError` that escapes the tool is rewritten by the middleware to `Token exchange failed (<code>)`. Catch it and raise your own `ToolError` (`ResourceError` or `PromptError` in a resource or prompt) and the message is left as it is. See [Failed token exchanges](./docs/Configuration.md#failed-token-exchanges).

```python
from auth0_ai_mcp import ApiError, DownscopedTokenError
from fastmcp.exceptions import ToolError

@mcp.tool
@with_required_scopes("tool:get_forecast")
async def get_forecast(location: str) -> dict:
    client = require_caller_mcp_client()
    try:
        token = await client.get_token_on_behalf_of(audience="https://weather-api/", scope="read:weather")
    except DownscopedTokenError as exc:
        raise ToolError("The weather API gave this server less access than the tool needs") from exc
    except ApiError as exc:
        raise ToolError(f"Could not get a token for the weather API ({exc.code})") from exc
    ...
```

Use `ResourceError` in a resource and `PromptError` in a prompt the same way.

## Acting as the server

For calls the server makes as itself, with no user involved. See [Server-identity calls](https://github.com/auth0/auth0-ai-python/blob/main/packages/auth0-ai-mcp/docs/OnBehalfOf.md#server-identity-calls-client-credentials).

```python
@mcp.tool
@with_required_scopes("tool:run_report")
async def run_report() -> dict:
    client = require_caller_mcp_client()
    token = await client.get_client_credentials_token(audience="https://internal-api/", scope="run:reports")
    # The caller only needs tool:run_report. The report runs as the server.
    ...
```

## Calling a third-party API with Token Vault

The user must have linked the account first, otherwise Auth0 answers `federated_connection_refresh_token_not_found`. In organization mode the vault entry is the organization's own, separate from the one used without an organization. See [Token Vault](https://github.com/auth0/auth0-ai-python/blob/main/packages/auth0-ai-mcp/docs/TokenVault.md).

```python
@mcp.tool
@with_required_scopes("tool:list_calendar_events")
async def list_calendar_events() -> list[dict]:
    client = require_caller_mcp_client()
    try:
        token = await client.get_token_for_connection(connection="google-oauth2")
    except ApiError as exc:
        if exc.code == "federated_connection_refresh_token_not_found":
            raise ToolError("Link your Google account first") from exc
        raise
    # Call the Google Calendar API with token["access_token"].
    ...
```

## Combining Token Vault with your own API in one tool

Ask for every token before doing any work, so a user who has not linked the account is told before anything is read or sent. Handle `ApiError` as in the two sections above to show a clearer message than `Token exchange failed (<code>)`.

```python
@mcp.tool
@with_required_scopes("tool:email_order_summary")
async def email_order_summary(order_id: str) -> dict:
    client = require_caller_mcp_client()
    google = await client.get_token_for_connection(connection="google-oauth2")
    orders = await client.get_token_on_behalf_of(audience="https://orders.api/", scope="read:orders")
    # Read the order with orders["access_token"], then create the Gmail draft with google["access_token"].
    ...
```

## Caching exchanged tokens

Set `token_store` and repeated exchanges for the same user, audience and scopes reuse the saved token. See [Scope matching for cached OBO tokens](./docs/Configuration.md#scope-matching-for-cached-obo-tokens), and [Token Caching](https://github.com/auth0/auth0-ai-python/blob/main/packages/auth0-ai-mcp/docs/TokenCaching.md) for a [Redis store](https://github.com/auth0/auth0-ai-python/blob/main/packages/auth0-ai-mcp/docs/TokenCaching.md#a-redis-store).

```python
import os

import redis.asyncio as redis

auth0 = Auth0FastMCP(Auth0FastMCPOptions(
    domain="your-tenant.auth0.com",
    resource_url="https://your-api.example.com",
    tool_scopes=["tool:read_orders"],
    client_id="YOUR_CLIENT_ID",
    client_secret="YOUR_CLIENT_SECRET",
    token_store=RedisTokenStore(redis.from_url(os.environ["REDIS_URL"]), secret=os.environ["TOKEN_STORE_SECRET"]),
))
```

## Accepting only one organization

`organization_id` takes one organization or a list. See [Organization policy](./docs/Configuration.md#organization-policy).

```python
auth0 = Auth0FastMCP(Auth0FastMCPOptions(
    domain="your-tenant.auth0.com",
    resource_url="https://your-api.example.com",
    tool_scopes=["tool:whoami"],
    organization_policy="required",
    organization_id=["org_abc", "org_xyz"],
))

@mcp.tool
async def whoami() -> dict:
    principal = get_caller_principal()
    return {"sub": principal.sub, "org_id": principal.org_id}
```

## Requiring a scope on every request

Use `required_scopes` for a scope every caller needs and `with_required_scopes` for a scope one tool needs. See [Required scopes](./docs/Configuration.md#required-scopes).

```python
auth0 = Auth0FastMCP(Auth0FastMCPOptions(
    domain="your-tenant.auth0.com",
    resource_url="https://your-api.example.com",
    required_scopes=["mcp:access"],
    tool_scopes=["tool:read_orders"],
))
```

## Checking a second scope inside a tool

Use `require_scopes` when only part of a tool needs a stronger scope.

```python
@mcp.tool
@with_required_scopes("tool:read_orders")
async def get_order(order_id: str, include_payment: bool = False) -> dict:
    if include_payment:
        require_scopes(get_caller_principal(), "read:payments")
    ...
```

## Runnable version

A complete runnable server using this pattern lives in [`examples/b2b_ecommerce`](./examples/b2b_ecommerce/).
