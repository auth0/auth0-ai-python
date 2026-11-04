# Code Style

## Naming

- `snake_case` functions, methods, and options. `PascalCase` classes. `UPPER_SNAKE` module constants (`_METHODS_WITHOUT_CALLER`).
- Private helpers live in `utils/_internal/`, one file per topic (`validation.py`, `telemetry.py`), with no leading underscore on the functions. Public modules call them through the module, for example `validation.resolve_audience(...)`, and never import a helper by name. Module constants carry a leading underscore.
- Type hints use builtin generics and `X | None` unions. ruff `UP` targets py310, so do not import `Optional` or `Union`.
- Modules start with `from __future__ import annotations`, except `__init__.py`.

## Errors

This package defines no error classes of its own. `Auth0TokenVerifier` turns `VerifyAccessTokenError` into a rejected token and re-raises `AuthServerUnavailableError`. `Auth0ContextMiddleware` raises `UnauthenticatedError` when a request has no verified token. Do not wrap core SDK errors.

Keep messages generic when they reach a client, and never put token material or scope lists in them. The one exception is the `403` FastMCP sends for `required_scopes`, which names the missing scope and is not written by this package.

## Patterns

- **Constructor wiring:** `Auth0FastMCP` builds the `McpServerClient`, the token verifier, and the context middleware from `Auth0FastMCPOptions`. New options are forwarded there.
- **Async I/O:** `verify_token` and `on_request` are `async def`.
- **Docstrings:** Google style with `Args:` / `Returns:` / `Raises:` sections, as in `Auth0ContextMiddleware.on_request`.
- **Placement:** put new code next to related code or at the end, never at an arbitrary position.

## Comments and docstrings

Enforced on every change (code, tests, docs, commit messages):

1. **Comments earn their place.** Only a non-obvious why, such as a protocol citation (`# RFC 9728`), a security decision, or an intentional omission. Never restate the line below. Default to one sharp line or none.
2. **Docstring format.** One-line description, then `Args`, then `Returns` / `Raises`. No design rationale, that belongs in the PR description.
3. **Plain hyphens only.** No em or en dashes in comments, docstrings, commit messages, or Markdown.
4. **No semicolon clause-splicing.** Split independent clauses into separate sentences.
5. **No internal references.** No ticket numbers, planning-doc paths, internal links, or comparisons with other SDKs.
6. **Helpers stay grouped.** Never interleave a private helper between public methods.
