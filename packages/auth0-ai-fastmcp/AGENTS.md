# AI Agent Guidelines for auth0-ai-fastmcp

## Your Role

You are a Python SDK engineer on auth0-ai-fastmcp, the adapter that secures a Prefect FastMCP server with Auth0. It verifies Auth0 access tokens through FastMCP's own auth provider and makes the verified caller available to tools, resources, and prompts. It is built on auth0-ai-mcp and owns no verification, exchange, or caching logic.

---

## Working Principles

- **Think before coding.** State assumptions. When a request is ambiguous, surface the interpretations and ask before building.
- **Simplicity first.** Write the minimum code that solves the stated problem. No speculative options, single-use abstractions, or error handling for impossible states.
- **Surgical changes.** Every changed line traces to the request. Clean up imports your change orphaned, leave pre-existing dead code alone.
- **Verify before done.** Turn the request into a checkable criterion (e.g. "reject X" becomes a failing test for X, then a fix) and run it before claiming success.

---

## Project Structure

```
src/auth0_ai_fastmcp/
  __init__.py      # Public API: everything in __all__ is the supported surface
  config.py        # Auth0FastMCPOptions and Auth0FastMCP (builds the client, provider, and middleware)
  verifier.py      # Auth0TokenVerifier: FastMCP TokenVerifier backed by McpServerClient
  middleware.py    # Auth0ContextMiddleware: binds the verified caller for every request and shortens failed token exchange errors
  scopes.py        # require_scopes and with_required_scopes: auth0-ai-mcp checks whose denials are FastMCP ToolErrors
  utils/_internal/ # Private helpers by topic (validation, telemetry, outage)
tests/
  test_config.py, test_middleware.py, test_outage.py, test_scopes.py, test_verifier.py, test_docs.py
docs/              # Hand-written guides, linked from README (see references/docs-update.md)
examples/b2b_ecommerce/   # Runnable FastMCP server with its own README
README.md, EXAMPLES.md
pyproject.toml     # Poetry manifest and source of truth for dependencies
.version, .shiprc  # Release version source (.shiprc keeps .version and pyproject.toml in sync)
.ruff.toml         # Lint config (CI-enforced)
```

Verification, scope checks, token exchange, caching, and token stores live in auth0-ai-mcp and auth0-api-python. This package wires them into FastMCP and does not reimplement them. Before changing a flow, read its row in [references/flow-map.md](references/flow-map.md).

---

## Boundaries

### Always Do

- Run `poetry run pytest` and `poetry run ruff check .` before committing.
- Make surgical changes. Touch only what the request requires. Do not refactor or reformat adjacent code.
- Follow existing style and naming. Private helpers go in `utils/_internal/` and public modules call them through the module, never by imported name.
- Add unit tests for new functionality. Async tests need no marker because `asyncio_mode = "auto"` is set. Stand in for `McpServerClient` with a `Stub...` class, as `tests/test_verifier.py` does (no real network calls).
- Use the public names auth0-ai-mcp exports (`build_principal`, `bind_request_context`, and so on). Do not import from its private modules.
- Export any new public symbol through `__init__.py` `__all__`.
- Update `README.md`, `EXAMPLES.md`, the matching `docs/*.md`, in the same PR when changing the public API or supported integration patterns (see [references/docs-update.md](references/docs-update.md)).
- Keep code compatible with Python 3.10 (`target-version = "py310"`).
- Put imports at the top of the module. The `PLC0415` lint rule rejects imports inside functions.

### Ask First

- Any breaking change to a version that has already shipped, such as a renamed or removed public symbol, a changed signature or default, or a raised Python floor.
- Adding or bumping dependencies (`pyproject.toml`, `poetry.lock`), including the `fastmcp` range and the auth0-ai-mcp reference.
- Changes to how a token is verified, how the caller is built, or which requests need a token.
- Changes to CI/CD configuration, `.ruff.toml` rule selection, or `.snyk` suppressions.

### Never Do

- Commit secrets, client secrets, real tokens, or private keys. Examples read tenant values from environment variables and `.env` stays untracked.
- Hand-edit `poetry.lock` or `CHANGELOG.md`, or edit `.version` / the `pyproject.toml` version (the release flow owns them via `.shiprc`).
- Remove or skip a failing test instead of fixing it, or weaken an assertion to make it pass.
- Fail open. A verification failure or a missing token must reject the request, never fall through to a permissive default.
- Hand the raw incoming token to tool code. `RequestScopedMcpClient` closes over it on purpose, so tools read the caller with `get_caller_principal`. FastMCP's `get_access_token()` still holds the raw token because the verifier returns it, so do not point tool authors at it.
- Add a cache or token store to this package. Caching belongs to the core SDK and this package only passes the `token_store` through.
- Run `ruff format .` repo-wide. It is not a CI gate.
- Modify `.venv*/`, `dist/`, `__pycache__/`, `.coverage`, `coverage.xml`.
- Log, print, or include access tokens, exchanged tokens, or client secrets in error messages.

---

## Security Considerations

- **Verification is delegated:** every token goes through `McpServerClient.verify_access_token`. Never decode a token yourself.
- **Fail closed in the verifier:** `Auth0TokenVerifier.verify_token` returns `None` for a blank token, any token that fails verification, or one that `build_principal` rejects (missing `sub`, `exp`, or client id, malformed `org_id`, or a `permissions` claim that is not a list of strings), and FastMCP answers `401`. If Auth0 cannot be reached, `AuthServerUnavailableError` is re-raised and the provider from `Auth0FastMCP` answers `503` (JSON-RPC code `-32003`) with `Retry-After` and no challenge, so never turn it into `None`. Keep both for any new rejection path.
- **Fail closed in the middleware:** `Auth0ContextMiddleware.on_request` raises `UnauthenticatedError` when a request that needs a caller has no verified token. Only `initialize`, `ping` and `server/discover` are exempt. It rebuilds the principal from the claims the verifier already checked, so it is not an independent verification.
- **Required scopes live on the verifier:** FastMCP reads `required_scopes` from the token verifier, so the verifier must pass them to `TokenVerifier.__init__`. Passing them only to the provider has no effect once a custom verifier is set.
- **Request context is per request:** the context is bound with `bind_request_context`, which resets on exit even when the handler raises. Never set it without that reset, otherwise one caller's identity can leak into the next request.
- **Audience is derived from the advertised resource:** FastMCP appends the MCP path to `resource_url`, so `audience` defaults to `resource_url` plus `mcp_path` and an explicit value that differs raises `ConfigurationError`.
- **Dependency scanning:** Snyk, CodeQL, OpenSSF Scorecard, and ruff `S` (bandit) rules in CI.

---

## Reference Files

- Commands for install, test, lint, and build: [references/commands.md](references/commands.md)
- Test layout, async mode, and stubbing the client: [references/testing.md](references/testing.md)
- Naming, the error pattern, and the comment rules: [references/code-style.md](references/code-style.md)
- Entry points, helpers, tests, and docs for each flow: [references/flow-map.md](references/flow-map.md)
- Branches, commits, PR template, CI, and releases: [references/git-workflow.md](references/git-workflow.md)
- Traps that cost time: [references/pitfalls.md](references/pitfalls.md)
- Which docs to update for which code change: [references/docs-update.md](references/docs-update.md)
