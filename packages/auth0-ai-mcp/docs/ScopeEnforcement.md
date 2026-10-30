# Scope Enforcement

Scope enforcement gates a tool on the scopes the caller holds in their incoming token - the authorization they were granted for your MCP server - before the tool body runs.

This is separate from the scopes of any downstream token minted by the On-Behalf-Of exchange. See [On-Behalf-Of](./OnBehalfOf.md) for downstream token scopes.

## Decorator form

`with_required_scopes(scopes)` is a decorator for async tool handlers. It reads the verified caller from the request context and checks the scopes before the tool body runs. `scopes` is one scope as a string or several as a list.

```python
from auth0_ai_mcp import with_required_scopes

@with_required_scopes(["read:orders", "read:payments"])
async def get_order_summary(order_id: str) -> dict:
    ...
```

If the caller has no context entry at all (called outside a request), it raises `UnauthenticatedError`. If any of the listed scopes is missing from `principal.scopes`, it raises `InsufficientScopeError`.

A string is always one scope, so pass a list when several are needed. An empty string, an empty list, or a list with a blank or non-string item raises `ConfigurationError`. `with_required_scopes` takes a single argument, so passing several separate arguments, such as `with_required_scopes("a", "b")`, raises `TypeError`.

## Imperative form

`require_scopes(principal, scopes)` is the imperative version. Pass the `Principal` yourself, which is useful when you have already fetched the caller and want to check a secondary scope partway through a tool.

```python
from auth0_ai_mcp import get_caller_principal, require_scopes

async def my_tool() -> dict:
    principal = get_caller_principal()
    require_scopes(principal, "write:orders")
    ...
```

The same error rules apply: `UnauthenticatedError` when `principal` is `None`, `InsufficientScopeError` when a scope is missing.

## Errors

Both `with_required_scopes` and `require_scopes` raise from `auth0_ai_mcp`:

- `UnauthenticatedError` - no caller in context (adapter did not run, or called outside a request).
- `InsufficientScopeError` - caller is authenticated but is missing one or more required scopes.
- `ConfigurationError` - the `scopes` argument is empty or malformed.

These errors are raised inside the tool, so the MCP framework reports them as a tool error and the HTTP response is still successful. Each scope denial is logged at INFO.

## Tenant-side setup: scopes must be in the client-grant

`with_required_scopes` checks `principal.scopes`, which comes from the incoming token. Scope checks read only the `scope` claim and never the RBAC `permissions` claim. Auth0 only includes a scope in a token if two things are true: the scope is registered on the API (resource server), and the MCP client's client-grant explicitly lists it.

Registering a scope on the API is not enough on its own. If the client-grant for your MCP client does not include the scope, Auth0 will not issue it in the token and the scope check will fail for every caller, even after a fresh login.

The same applies to RBAC permissions. A client that requests no scopes gets a token with an empty `scope` claim, so the check fails even when the user holds the permission. The MCP client has to request the scope at login, which it does when you advertise it in `scopes_supported`.

When you add a new gated tool:

1. Register the new scope on your MCP API.
2. Update the client-grant for the MCP client to include it.

```bash
# List existing grants to find the right grant ID
auth0 api get "client-grants?audience=YOUR_MCP_AUDIENCE"

# Patch the grant with the full updated scope list
auth0 api patch "client-grants/YOUR_GRANT_ID" \
  --data '{"scope":["read:orders","write:orders"]}'
```

> [!IMPORTANT]
> A grant update replaces the whole scope list, so include every existing scope plus the new one.

After updating the grant, users must re-authenticate so the new token carries the added scope.

## Related

- [Request Context](./RequestContext.md) - how the caller ends up in context and the accessor functions.
- [Token Verification](./TokenVerification.md) - how `principal.scopes` is populated from the incoming token.
- [On-Behalf-Of](./OnBehalfOf.md) - the separate exchange that mints downstream tokens.
