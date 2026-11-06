# Tool Scopes

`tool_scopes` are advertised in the server's protected-resource metadata so the MCP client knows to request them at login. `with_required_scopes` and `require_scopes` then check them on the tools, resources and prompts you choose to protect.

> [!IMPORTANT]
> `tool_scopes` only advertises scopes and does not protect anything. A tool still needs `with_required_scopes` or `require_scopes` to enforce them.

## Two separate scope layers

There are two distinct authorization layers at play in an `auth0-ai-fastmcp` server.

The first layer is the MCP server's own tool authorization. The scopes you list in `tool_scopes` are included in the RFC 9728 protected-resource metadata under `scopes_supported`, and so is every scope in `required_scopes`. With the provider from `Auth0FastMCP`, the `401` that an unauthenticated request gets names the same scopes in its `WWW-Authenticate` header. When an MCP client connects, it reads the metadata or that header and requests those scopes during the login flow. List every scope your clients need, whether it gates a tool, a resource or a prompt. The `with_required_scopes` decorator enforces them on a tool. If the caller's token does not carry a required scope, the tool call is rejected before it runs.

The second layer is downstream API authorization. When a tool needs to call an external API on behalf of the caller, it uses `get_token_on_behalf_of` from `auth0-ai-mcp` to mint a separate token scoped to that API. Those downstream scopes (like `read:orders`) are entirely separate from the `tool:*` scopes that gate the tool itself. See [On-Behalf-Of](https://github.com/auth0/auth0-ai-python/blob/main/packages/auth0-ai-mcp/docs/OnBehalfOf.md) for how that exchange works.

## Example: gating a tool

`mcp` is the server from [Configuration](./Configuration.md), created with `auth=auth0.provider`.

```python
from auth0_ai_fastmcp import with_required_scopes


@mcp.tool
@with_required_scopes("tool:read_orders")
async def read_orders() -> list[dict]:
    ...
```

With `tool_scopes=["tool:read_orders", "tool:place_order"]` set on `Auth0FastMCPOptions`, both scopes appear in the server's metadata, so the MCP client requests them at login. The decorator ensures only callers whose token includes `tool:read_orders` can invoke `read_orders`. For the full server, including the downstream token exchange, see [Examples](../EXAMPLES.md#full-server-example).

## Gating resources and prompts

`with_required_scopes` also works on async resource and prompt handlers. A handler can instead call `require_scopes(get_caller_principal(), "<scope>")` at the top. See [Resources and prompts](../EXAMPLES.md#resources-and-prompts) for a resource and a prompt that do this.

To require a scope on every request instead, use `required_scopes` in [Configuration](./Configuration.md#required-scopes).

Import `with_required_scopes` and `require_scopes` from `auth0_ai_fastmcp`, not `auth0_ai_mcp`. They raise the same `InsufficientScopeError` and `UnauthenticatedError`, which are also FastMCP `ToolError`s. A denied tool call reaches the client as a tool error in a normal `200` response, not an HTTP `403`, and carries the reason even when `mask_error_details` is on, and the server logs the denial at INFO instead of ERROR. A denied resource or prompt is still logged with a traceback by FastMCP. Matching is exact, including case, so a broader scope does not imply a narrower one. Put `@mcp.tool` above `@with_required_scopes`, otherwise FastMCP registers the unguarded function. The wrappers do not cover `require_caller_*`. For the scope rules, see [Scope Enforcement](https://github.com/auth0/auth0-ai-python/blob/main/packages/auth0-ai-mcp/docs/ScopeEnforcement.md).
