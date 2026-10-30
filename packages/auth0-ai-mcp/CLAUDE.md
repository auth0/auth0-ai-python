# AI Agent Guidelines for auth0-ai-mcp

## Your Role

You are a Python SDK engineer on auth0-ai-mcp, the async library MCP servers use to verify Auth0 access tokens, enforce scopes, and exchange the caller's token for downstream API tokens. It is built on auth0-api-python and owns no MCP framework.

---

## Working Principles

- **Think before coding.** State assumptions. When a request is ambiguous, surface the interpretations and ask before building.
- **Simplicity first.** Write the minimum code that solves the stated problem. No speculative options, single-use abstractions, or error handling for impossible states.
- **Surgical changes.** Every changed line traces to the request. Clean up imports your change orphaned, leave pre-existing dead code alone.
- **Verify before done.** Turn the request into a checkable criterion (e.g. "reject X" becomes a failing test for X, then a fix) and run it before claiming success.

---

## Project Structure

```
src/auth0_ai_mcp/
  __init__.py                # Public API: everything in __all__ is the supported surface
  client.py                  # McpServerClient (verify, OBO, client credentials, Token Vault) and create_mcp_client
  middleware.py              # Auth0AsgiMiddleware and build_protected_resource_metadata. Not in __all__, import from auth0_ai_mcp.middleware
  principal.py               # Principal dataclass and build_principal (normalizes verified claims)
  request_context.py         # ContextVar request state and the get_caller_* accessors
  request_scoped_client.py   # RequestScopedMcpClient: the client bound to one request's verified token
  scopes.py                  # require_scopes and the with_required_scopes decorator
  errors.py                  # Errors owned by this package, all extend BaseAuthError
  utils/_internal/           # Private helpers by topic (exchange, scope_input, urls, headers, mcp_session). A public helper is a plain-named file in utils/
tests/
  test_client.py, test_middleware.py, test_principal.py, test_request_context.py, test_scopes.py
docs/                        # Hand-written guides, linked from README (see references/docs-update.md)
examples/b2b_ecommerce/      # Runnable server (server.py, tools.py, token_store.py) with its own README
README.md, EXAMPLES.md
pyproject.toml               # Poetry manifest and source of truth for dependencies
.version, .shiprc            # Release version source (.shiprc keeps .version and pyproject.toml in sync)
.ruff.toml                   # Lint config (CI-enforced)
```

Token verification, the OBO exchange, caching, and token stores live in auth0-api-python. This package wraps them and does not reimplement them. Before changing a flow, read its row in [references/flow-map.md](references/flow-map.md) for entry points, supporting helpers, tests, and docs.

---

## Boundaries

### Always Do

- Run `poetry run pytest` and `poetry run ruff check .` before committing (both run in CI on Python 3.10 to 3.12).
- Make surgical changes: touch only what the request requires. Do not refactor or reformat adjacent code.
- Follow existing style and naming. Private helpers go in `utils/_internal/` and public modules call them through the module, never by imported name. Never reorder existing declarations.
- Add unit tests for new functionality. Async tests need no marker because `asyncio_mode = "auto"` is set. Stand in for the core client with a `Stub...` class, as `tests/test_client.py` does (no real network calls).
- Raise typed errors from `errors.py` (subclasses of `BaseAuthError` with `get_status_code()` / `get_error_code()`). Let the core SDK's own errors propagate unchanged. Never return `None` or a bare `dict` to signal failure.
- Export any new public symbol through `__init__.py` `__all__`.
- Update `README.md`, `EXAMPLES.md`, and the matching `docs/*.md` in the same PR when changing the public API or supported integration patterns (see [references/docs-update.md](references/docs-update.md)).
- Keep code compatible with Python 3.10 (`target-version = "py310"`).
- Put imports at the top of the module. The `PLC0415` lint rule rejects imports inside functions, and `TYPE_CHECKING` blocks are the place for typing-only imports.

### Ask First

- Any breaking change to a version that has already shipped. Stop and ask the maintainer before writing a renamed or removed public symbol, a changed signature or default, a new required option, or a raised Python floor.
- Changing an existing error's `get_error_code()` string or `get_status_code()`. Integrators branch on these, so treat them as public API.
- Adding or bumping dependencies (`pyproject.toml`, `poetry.lock`), including the `auth0-api-python` pin.
- Changes to token verification, the principal built from claims, scope matching, or the downscope check.
- Changes to CI/CD configuration (`.github/workflows/`, `.github/actions/`), `.ruff.toml` rule selection, or `.snyk` suppressions.

### Never Do

- Commit secrets, client secrets, real tokens, or private keys. Examples read tenant values from environment variables.
- Hand-edit `poetry.lock` or `CHANGELOG.md`, or edit `.version` / the `pyproject.toml` version (the release flow owns them via `.shiprc`).
- Remove or skip a failing test instead of fixing it, or weaken an assertion to make it pass.
- Fail open. A verification, scope, exchange, or missing-context failure must raise a typed error or return a `401` challenge, never fall through to a permissive default.
- Hand the raw incoming token to tool code. `RequestScopedMcpClient` closes over it on purpose.
- Add a cache or token store to this package. Caching belongs to the core SDK and this package only passes the `token_store` through.
- Run `ruff format .` repo-wide. It is not a CI gate and the tree is not format-clean (see [references/pitfalls.md](references/pitfalls.md)).
- Modify `.venv*/`, `dist/`, `__pycache__/`, `.coverage`, `coverage.xml`.
- Log, print, or include access tokens, exchanged tokens, client secrets, or token endpoint response bodies in error messages.
- Break backward compatibility without asking first and getting explicit approval.

---

## Security Considerations

- **Verification is delegated:** every token goes through `McpServerClient.verify_access_token`, which calls the core SDK. Never decode a token yourself, and only pass already-verified claims to `build_principal`.
- **Fail closed in the middleware:** a missing, blank or non-Bearer token gets a `401` with a bare challenge, and a token that fails verification (including a claim set `build_principal` rejects) gets a `401` with `invalid_token`. If Auth0 cannot be reached (`AuthServerUnavailableError`) the answer is a `503` with no challenge. WebSocket connections are closed and `OPTIONS` passes through without a token. The tool never runs, so keep it that way for any new rejection path.
- **Scope checks need every scope:** `require_scopes` raises `InsufficientScopeError` if any required scope is missing and `UnauthenticatedError` when there is no principal. `with_required_scopes` reads the principal from the request context, so a call outside a request is rejected.
- **Downscope detection:** `exchange.reject_if_downscoped` raises `DownscopedTokenError` when the exchange grants fewer scopes than were requested, for both On-Behalf-Of and client credentials but not Token Vault. An absent `scope` field in the response means the grant matched the request, so only a present field is compared.
- **Expired results are rejected:** after every exchange `exchange.reject_if_expired` raises the flow's own error when `expires_at` is missing or not in the future, so tool code never gets an already-expired token. Any leeway for clock skew belongs in the core SDK.
- **Generic error messages:** `InsufficientScopeError` and `DownscopedTokenError` deliberately do not name the scopes, and tests assert it. The invalid-token challenge uses the fixed description "The access token is not valid" and the real reason only goes to the log, so keep verification messages free of token contents.
- **Token stores:** a store is the integrator's `AbstractTokenStore`, and the base class encrypts values with a secret of at least 32 characters. Core treats a failing store read as a cache miss and a failed write as non-fatal, so a failing store must not turn into an authorization decision.
- **Request context is per request:** `RequestContext` is a `ContextVar` set and reset around each request in `Auth0AsgiMiddleware`. Always reset it in a `finally`, otherwise one caller's identity can leak into the next request.
- **Dependency scanning:** Snyk (`sca_scan.yml`), CodeQL (`codeql.yml`), OpenSSF Scorecard (`scorecard.yml`), and ruff `S` (bandit) rules in CI.

---

## Reference Files

- Commands for install, test, lint, and build: [references/commands.md](references/commands.md)
- Test layout, async mode, and stubbing the core client: [references/testing.md](references/testing.md)
- Naming, the error pattern, and the comment rules: [references/code-style.md](references/code-style.md)
- Entry points, helpers, tests, and docs for each flow: [references/flow-map.md](references/flow-map.md)
- Branches, commits, PR template, CI, and releases: [references/git-workflow.md](references/git-workflow.md)
- Traps that cost time: [references/pitfalls.md](references/pitfalls.md)
- Which docs to update for which code change: [references/docs-update.md](references/docs-update.md)
