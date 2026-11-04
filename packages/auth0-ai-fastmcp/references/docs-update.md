# Docs Update Rules

A PR that changes public API, configuration, or integration patterns is not complete until the matching docs are updated in the same PR.

## Tracked docs

| Doc | Covers |
|-----|--------|
| `README.md` | Install, wiring the provider and middleware, writing a gated tool, links to the guides |
| `EXAMPLES.md` | Server setup, gated tools, resources and prompts, the b2b_ecommerce example |
| `docs/Configuration.md` | Every `Auth0FastMCPOptions` field, how requests are verified, the errors callers see |
| `docs/ToolScopes.md` | Tool scopes, `with_required_scopes`, `require_scopes` |
| `examples/b2b_ecommerce/README.md` | Running the example server |

## When you change code, update these docs

| When this changes | Update |
|-------------------|--------|
| An `Auth0FastMCPOptions` field added, removed, renamed, or its default changes | `docs/Configuration.md`. Then check the README and `EXAMPLES.md` snippets still match |
| Verification behavior or which tokens are rejected | `docs/Configuration.md` |
| Which requests get a caller, or the missing-token behavior | `README.md` "Configure Auth0FastMCP", `docs/Configuration.md` |
| Required scopes or tool scopes | `docs/Configuration.md`, `docs/ToolScopes.md` |
| Token store, scope matching, or OBO options | `docs/Configuration.md` |
| New exported symbol in `__init__.py` | `EXAMPLES.md` (add a usage sample) |
| The `fastmcp` range or the supported Python version | `pyproject.toml` and, if the README states the range, `README.md` |
| The auth0-ai-mcp API this package calls | Check `docs/` here still matches |

State each fact in one doc and link to it from the others rather than repeating it. When a fact changes, update the page that owns it, then check the pages that link to it. The README keeps a one-line callout at most, and the detail lives in `docs/`.

Use GitHub alerts (`> [!IMPORTANT]`, `> [!WARNING]`) only for things that fail silently or widen access, at most one or two per page. Put the alert type alone on the first line and the text on the next. Errors that fail loudly stay plain text.

Links to auth0-ai-mcp guides use absolute GitHub URLs, because this package is published separately.
