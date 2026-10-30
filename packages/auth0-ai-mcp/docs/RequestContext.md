# Request Context

The adapter sets a per-request `contextvar` after verifying the incoming token, so tool code can read the verified caller without taking an auth argument.

## Accessor functions

All four accessors are importable from `auth0_ai_mcp`:

```python
from auth0_ai_mcp import (
    get_caller_principal,
    require_caller_principal,
    get_caller_mcp_client,
    require_caller_mcp_client,
)
```

- `get_caller_principal() -> Principal | None` - returns the verified `Principal` for the current request, or `None` when called outside a request (for example in a background task or test that has not set up a context).
- `require_caller_principal() -> Principal` - same as `get_caller_principal` but raises `UnauthenticatedError` instead of returning `None`.
- `get_caller_mcp_client() -> RequestScopedMcpClient | None` - returns the request-scoped client, or `None` outside a request.
- `require_caller_mcp_client() -> RequestScopedMcpClient` - same as above but raises `UnauthenticatedError` instead of returning `None`. Use this inside tool handlers where the adapter guarantees a caller is present, so you get a clear error rather than a silent `None`.

## RequestScopedMcpClient

`RequestScopedMcpClient` wraps the shared `McpServerClient` bound to one request's token and principal. It exposes four methods:

- `get_token_on_behalf_of(*, audience: str, scope: str | None = None) -> TokenSet` - exchanges the caller's incoming token for a downstream token scoped to `audience`. For what this exchange does and how the optional cache works in front of it, see [On-Behalf-Of](./OnBehalfOf.md) and [Token Caching](./TokenCaching.md).
- `get_client_credentials_token(*, audience: str, scope: str | None = None) -> TokenSet` - see [On-Behalf-Of](./OnBehalfOf.md#server-identity-calls-client-credentials).
- `get_token_for_connection(*, connection: str, login_hint: str | None = None) -> TokenSet` - see [Token Vault](./TokenVault.md).
- `get_principal() -> Principal` - returns the verified `Principal` for this request.

The incoming token is closed over inside `RequestScopedMcpClient`, so a tool cannot accidentally forward or leak it.

## Setting the context (adapters)

Adapters set the context with the `bind_request_context(context)` context manager and a `RequestContext(principal=..., mcp_client=...)`, both importable from `auth0_ai_mcp`. See [Writing an Adapter](./WritingAnAdapter.md#3-build-and-set-the-request-context).

## Example

```python
from auth0_ai_mcp import get_caller_principal, require_caller_mcp_client

principal = get_caller_principal()      # principal.sub, principal.scopes, principal.org_id
auth0 = require_caller_mcp_client()     # request-scoped client for token exchanges
```

## Related

- [Token Verification](./TokenVerification.md) - how the `Principal` is built and placed in context.
- [Scope Enforcement](./ScopeEnforcement.md) - gating a tool on the caller's scopes before reading context.
- [On-Behalf-Of](./OnBehalfOf.md) - the token exchange triggered by `get_token_on_behalf_of`.
