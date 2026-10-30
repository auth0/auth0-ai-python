# Token Verification

Every incoming bearer token is verified against Auth0 before an MCP handler runs. A request without a token, or a token that fails verification, gets a `401` and never reaches a tool. See [What the middleware returns](#what-the-middleware-returns).

## How verification works

Verification runs inside the adapter via `auth0-api-python`. The library checks the signature against the tenant's JWKS, plus `exp`, `iss` and `aud`. `McpServerClient.verify_access_token(token)` returns a `VerifiedToken` whose `claims` hold the verified claims. The adapter then builds a `Principal` with `build_principal`, which also checks `sub`, and sets it in the per-request `contextvar`. On failure it short-circuits the request with a `401` before any tool code runs. The organization policy also applies during verification, see [Organization Policy](./OrganizationPolicy.md).

The adapter also serves the RFC 9728 `/.well-known/oauth-protected-resource` metadata document, which tells clients where to find the authorization server for your resource.

## The Principal dataclass

`Principal` is a dataclass built from the verified token's claims. Tool code normally reads it through the request context (see [Request Context](./RequestContext.md)) rather than constructing one directly.

```python
from auth0_ai_mcp import Principal
```

Fields:

- `sub` (`str`): the subject claim identifying the caller.
- `expires_at` (`int | float`): unix epoch seconds the token expires, from the `exp` claim.
- `scopes` (`list[str]`): parsed from the space-separated `scope` claim. Empty list when the claim is absent.
- `permissions` (`list[str] | None`): from the `permissions` claim. `None` when the claim is absent (RBAC not enabled on the Auth0 API definition), an empty list or populated list when present.
- `client_id` (`str`): from the `azp` claim, falling back to `client_id`. Never `None`, because a token with neither is rejected with a `401`.
- `org_id` (`str | None`): from the `org_id` claim. `None` when the token carries no Organization.

`build_principal(claims)` (importable from `auth0_ai_mcp`) builds the `Principal` and raises `VerifyAccessTokenError` for a missing or blank `sub`, an `exp` that is missing, not a number, a boolean, or not finite, no `azp` or `client_id`, a `permissions` claim that is not a list of strings, or an `org_id` that is not a string.

## VerifyAccessTokenError

The middleware catches `VerifyAccessTokenError` (imported from `auth0-api-python`) and returns the `401` (or a `503` for its subclass `AuthServerUnavailableError`), so it is never raised to the caller. Tool code does not catch this error because the token is verified before any tool runs. You only need to handle it if you call `McpServerClient.verify_access_token` yourself in custom adapter code.

## What the middleware returns

The middleware answers each case as follows:

- No token, a blank `Bearer` value, or any scheme other than `Bearer` - a `401` with a bare challenge of the form `Bearer resource_metadata="<url>"` and no `error`. The body message is "Unauthorized". DPoP is not supported yet, so a `DPoP` authorization is treated as no token.
- A token that fails verification - a `401` with `error="invalid_token"` and the fixed description "The access token is not valid". The real reason is only written to the server log.
- Auth0 cannot be reached to fetch the signing keys - verification raises `AuthServerUnavailableError` and the middleware returns a `503` with `Retry-After: 5` and no `WWW-Authenticate` challenge, so the client keeps its token and retries.
- Any other `VerifyAccessTokenError` - a `401`. Any other exception propagates to the framework.
- A WebSocket connection - closed with code 1008.
- An `OPTIONS` request - passes through to the app without verification.

The `resource_metadata` value in the challenge is the path-suffixed metadata URL from RFC 9728. For example, a resource URL of `https://host/mcp` gives `https://host/.well-known/oauth-protected-resource/mcp`. The metadata document is served for `GET` only, at `/.well-known/oauth-protected-resource` and at the path-suffixed path.

When the `mcp` package is installed, the middleware also sets `scope["user"]` and `scope["auth"]` for the MCP session manager, with the raw token replaced by the literal "redacted".

To build the same header in custom code, use `build_www_authenticate(resource_metadata_url, error=None, error_description=None)`, imported from `auth0_ai_mcp.middleware`. It makes every value safe for a quoted header.

## Related

- [Request Context](./RequestContext.md) - reading the verified `Principal` inside a tool.
- [Organization Policy](./OrganizationPolicy.md) - requiring or filtering by `org_id`.
- [Writing an Adapter](./WritingAnAdapter.md) - how an adapter calls into the core verification logic.
