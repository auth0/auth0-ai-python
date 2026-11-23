# Examples

This page walks through a complete Auth0-secured MCP server using the ASGI adapter shipped with `auth0-ai-mcp`. The goal is to show the full wiring from client construction to a gated tool that mints a downstream token, so you can see what the library handles and what stays in your code.

- [Building the client](#building-the-client)
- [Wiring the ASGI adapter](#wiring-the-asgi-adapter)
- [Writing a gated tool](#writing-a-gated-tool)
- [Calling two downstream APIs from one tool](#calling-two-downstream-apis-from-one-tool)
- [Showing a useful message when an exchange fails](#showing-a-useful-message-when-an-exchange-fails)
- [Acting as the server](#acting-as-the-server)
- [Calling a third-party API with Token Vault](#calling-a-third-party-api-with-token-vault)
- [Combining Token Vault with your own API in one tool](#combining-token-vault-with-your-own-api-in-one-tool)
- [Caching exchanged tokens](#caching-exchanged-tokens)
- [Accepting only one organization](#accepting-only-one-organization)
- [Checking a second scope inside a tool](#checking-a-second-scope-inside-a-tool)
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

From this point on, the library verifies every incoming token, rejects bad ones with a `401` before any tool runs, and serves the protected resource metadata. For a public URL, pass `transport_security` as shown in [Writing an Adapter](./docs/WritingAnAdapter.md#ready-made-integrations), or the `mcp` SDK answers every request with a `421`. See [Token Verification](./docs/TokenVerification.md) and [Configuration](./docs/Configuration.md).

## Writing a gated tool

```python
from auth0_ai_mcp import require_caller_mcp_client, with_required_scopes

@mcp.tool()
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

Keep `@mcp.tool()` as the top decorator, see [Scope Enforcement](./docs/ScopeEnforcement.md#decorator-form). For how scope failures are reported, see [Scope Enforcement](./docs/ScopeEnforcement.md#errors).

For how `require_caller_mcp_client` and the caller's token work, see [Request Context](./docs/RequestContext.md#requestscopedmcpclient).

## Calling two downstream APIs from one tool

Ask once per downstream service, each with only its own scopes. See [On-Behalf-Of](./docs/OnBehalfOf.md).

```python
@mcp.tool()
@with_required_scopes("tool:cancel_order")
async def cancel_order(order_id: str) -> dict:
    auth0 = require_caller_mcp_client()
    orders = await auth0.get_token_on_behalf_of(audience="https://orders.api/", scope="cancel:orders")
    payments = await auth0.get_token_on_behalf_of(audience="https://payments.api/", scope="write:refunds")
    # Call the orders API with orders["access_token"], then the payments API with payments["access_token"].
    ...
```

## Showing a useful message when an exchange fails

Catch `ApiError` (the Auth0 error is in `code`) and `DownscopedTokenError` (Auth0 granted fewer scopes than asked) and raise a `ToolError`. Any other exception reaches the client as a bare `Error executing tool <name>`.

```python
from auth0_ai_mcp import ApiError, DownscopedTokenError
from mcp.server.mcpserver.exceptions import ToolError

@mcp.tool()
@with_required_scopes("read:weather")
async def get_forecast(location: str) -> dict:
    auth0 = require_caller_mcp_client()
    try:
        token = await auth0.get_token_on_behalf_of(audience="https://weather-api/", scope="read:weather")
    except DownscopedTokenError as exc:
        raise ToolError("The weather API gave this server less access than the tool needs") from exc
    except ApiError as exc:
        raise ToolError(f"Could not get a token for the weather API ({exc.code})") from exc
    ...
```

## Acting as the server

For calls the server makes as itself, with no user involved. See [Server-identity calls](./docs/OnBehalfOf.md#server-identity-calls-client-credentials).

```python
@mcp.tool()
@with_required_scopes("tool:run_report")
async def run_report() -> dict:
    auth0 = require_caller_mcp_client()
    token = await auth0.get_client_credentials_token(audience="https://internal-api/", scope="run:reports")
    # The caller only needs tool:run_report. The report runs as the server.
    ...
```

## Calling a third-party API with Token Vault

The user must have linked the account first, otherwise Auth0 answers `federated_connection_refresh_token_not_found`. In organization mode the vault entry is the organization's own, separate from the one used without an organization. See [Token Vault](./docs/TokenVault.md).

```python
@mcp.tool()
@with_required_scopes("tool:list_calendar_events")
async def list_calendar_events() -> list[dict]:
    auth0 = require_caller_mcp_client()
    try:
        token = await auth0.get_token_for_connection(connection="google-oauth2")
    except ApiError as exc:
        if exc.code == "federated_connection_refresh_token_not_found":
            raise ToolError("Link your Google account first") from exc
        raise
    # Call the Google Calendar API with token["access_token"].
    ...
```

## Combining Token Vault with your own API in one tool

Ask for every token before doing any work, so a user who has not linked the account is told before anything is read or sent. Handle `ApiError` as in the two sections above, otherwise the user only sees `Error executing tool <name>`.

```python
@mcp.tool()
@with_required_scopes("tool:email_order_summary")
async def email_order_summary(order_id: str) -> dict:
    auth0 = require_caller_mcp_client()
    google = await auth0.get_token_for_connection(connection="google-oauth2")
    orders = await auth0.get_token_on_behalf_of(audience="https://orders.api/", scope="read:orders")
    # Read the order with orders["access_token"], then create the Gmail draft with google["access_token"].
    ...
```

## Caching exchanged tokens

Pass a `token_store` and repeated exchanges for the same user, audience and scopes reuse the saved token. See [Token Caching](./docs/TokenCaching.md) for the store interface, a [Redis store](./docs/TokenCaching.md#a-redis-store) and the [scope-matching modes](./docs/TokenCaching.md#scope-matching-modes).

```python
import os

import redis.asyncio as redis

client = create_mcp_client(
    domain="your-tenant.auth0.com",
    audience="https://your-mcp-server/mcp",
    client_id="YOUR_CLIENT_ID",
    client_secret="YOUR_CLIENT_SECRET",
    token_store=RedisTokenStore(redis.from_url(os.environ["REDIS_URL"]), secret=os.environ["TOKEN_STORE_SECRET"]),
)
```

## Accepting only one organization

`organization_id` takes one organization or a list. See [Organization Policy](./docs/OrganizationPolicy.md).

```python
from auth0_ai_mcp import get_caller_principal

client = create_mcp_client(
    domain="your-tenant.auth0.com",
    audience="https://your-mcp-server/mcp",
    organization_policy="required",
    organization_id=["org_abc", "org_xyz"],
)

@mcp.tool()
async def whoami() -> dict:
    principal = get_caller_principal()
    return {"sub": principal.sub, "org_id": principal.org_id}
```

## Checking a second scope inside a tool

Use `require_scopes` when only part of a tool needs a stronger scope. See [Scope Enforcement](./docs/ScopeEnforcement.md#imperative-form).

```python
from auth0_ai_mcp import get_caller_principal, require_scopes

@mcp.tool()
@with_required_scopes("read:orders")
async def get_order(order_id: str, include_payment: bool = False) -> dict:
    if include_payment:
        require_scopes(get_caller_principal(), "read:payments")
    ...
```

## Complete example - b2b_ecommerce

The [`examples/b2b_ecommerce`](./examples/b2b_ecommerce/) directory contains a runnable server whose flagship `cancel_and_refund_order` tool touches two downstream services (orders and payments) in one call, minting a separate scoped token for each via On-Behalf-Of. It also shows:

- An in-memory `token_store` passed to `create_mcp_client` for caching OBO tokens, and `scope_matching` driven by an environment variable to switch between matching modes at deploy time. See [Token Caching](./docs/TokenCaching.md) for what a production store needs and the available modes.
- Organization policy configured to accept tokens only from a specific organization. The policy is optional and defaults to `"allow"`. See [Organization Policy](./docs/OrganizationPolicy.md).
