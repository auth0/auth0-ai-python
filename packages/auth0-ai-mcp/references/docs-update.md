# Docs Update Rules

A PR that changes public API, configuration, or integration patterns is not complete until the matching docs are updated in the same PR.

## Tracked docs

| Doc | Covers |
|-----|--------|
| `README.md` | Install, a short quick start, one callout for the `audience` rule, links to the guides |
| `EXAMPLES.md` | Runnable samples for building the client, the ASGI adapter, a gated tool, the b2b_ecommerce example |
| `docs/Configuration.md` | Every `create_mcp_client` and `Auth0AsgiMiddleware` option, the `audience` rule, `api_client` |
| `docs/TokenVerification.md` | How verification works, the `Principal` dataclass, `VerifyAccessTokenError` |
| `docs/ScopeEnforcement.md` | Decorator and imperative scope checks, errors, tenant-side client-grant setup |
| `docs/OnBehalfOf.md` | The OBO exchange inside a tool, downscope protection, client credentials |
| `docs/TokenVault.md` | `get_token_for_connection`, `login_hint`, Auth0 setup, linking an account |
| `docs/TokenCaching.md` | The store interface, cache key, scope-matching modes, the indexed store |
| `docs/OrganizationPolicy.md` | Organization modes, setting an organization ID, reading `org_id` |
| `docs/RequestContext.md` | The accessor functions and `RequestScopedMcpClient` |
| `docs/WritingAnAdapter.md` | The steps an adapter for another framework must follow |
| `examples/b2b_ecommerce/README.md` | Running the example server |

## When you change code, update these docs

| When this changes | Update |
|-------------------|--------|
| A public `McpServerClient` or `RequestScopedMcpClient` method added, removed, renamed, or its arguments change | `README.md`, `EXAMPLES.md`, the guide for that flow (see `references/flow-map.md`) |
| `create_mcp_client` parameter added, removed, or default changed | `docs/Configuration.md`, and `docs/TokenCaching.md` or `docs/OrganizationPolicy.md` for the related option. Then check the README and `EXAMPLES.md` snippets still match |
| Token store behavior or scope matching | `docs/TokenCaching.md` |
| Scope enforcement or the errors it raises | `docs/ScopeEnforcement.md` |
| Downscope detection or OBO behavior | `docs/OnBehalfOf.md` |
| Token Vault behavior or its errors | `docs/TokenVault.md` |
| `Principal` fields or claim handling | `docs/TokenVerification.md`, `docs/RequestContext.md` |
| Middleware behavior, challenge format, or metadata | `docs/TokenVerification.md` (what the middleware returns), `docs/Configuration.md` (metadata options), `docs/WritingAnAdapter.md` |
| A new error code or status | The guide for the flow that raises it |
| New exported symbol in `__init__.py` | `EXAMPLES.md` (add a usage sample) |
| Supported Python version or install method | `README.md` "Install" and `CONTRIBUTING.md` |

State each fact in one doc and link to it from the others rather than repeating it. When a fact changes, update the page that owns it, then check the pages that link to it. The README keeps a one-line callout at most, and the detail lives in `docs/`.

Use GitHub alerts (`> [!IMPORTANT]`, `> [!WARNING]`) only for things that fail silently or widen access, at most one or two per page. Put the alert type alone on the first line and the text on the next. Errors that fail loudly stay plain text.
