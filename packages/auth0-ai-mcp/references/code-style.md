# Code Style

## Naming

- `snake_case` functions, methods, and options. `PascalCase` classes. `UPPER_SNAKE` module constants (`_PRM_PATH`).
- Private helpers live in `utils/_internal/`, one file per topic (`exchange.py`, `urls.py`, `headers.py`), with no leading underscore on the functions. Public modules call them through the module, for example `exchange.reject_if_downscoped(...)`, and never import a helper by name. Private methods that need `self` (`_send_unauthorized`) stay on their class.
- Error classes end in `Error` and live in `errors.py`.
- Type hints use builtin generics and `X | None` unions. ruff `UP` targets py310, so do not import `Optional` or `Union`.
- Modules start with `from __future__ import annotations`, and typing-only imports go under `if TYPE_CHECKING:` (see `request_context.py`).

## Errors

Every error owned by this package subclasses `BaseAuthError` and defines its status and error code. They are raised inside the tool, so the framework reports them as a tool error:

```python
class DownscopedTokenError(BaseAuthError):
    """The exchange granted fewer scopes than were requested. Error code `downscoped_token`, status 403."""

    def get_status_code(self) -> int:
        return 403

    def get_error_code(self) -> str:
        return "downscoped_token"
```

Errors for the core SDK's own functions (`VerifyAccessTokenError`, `GetAccessTokenForConnectionError`, `GetClientCredentialsTokenError`, `ApiError`) are raised by the core SDK and pass through this package unchanged. Do not wrap them. Public errors are exported from `__init__.py`, so a new one is added to `__all__` as well.

Keep messages generic when they reach a client:

```python
# Good (utils/_internal/exchange.py, reject_if_downscoped)
raise DownscopedTokenError("Exchanged token did not include all requested scopes.")

# Bad
raise DownscopedTokenError(f"Missing scopes: {missing}, token: {result['access_token']}")
```

The bad version names the scopes and puts token material into a message that can reach an HTTP response.

## Patterns

- **Constructor wiring:** `create_mcp_client` builds an `ApiClient` from `ApiClientOptions` unless one is passed in, then wraps it in `McpServerClient`. New core options are forwarded there as keyword arguments.
- **Request-scoped access:** tool code reaches the caller through `get_caller_principal()` and `require_caller_mcp_client()`, never through an argument carrying the raw token.
- **Async I/O:** public verification and exchange methods are `async def`. The ASGI middleware is a plain ASGI callable.
- **Docstrings:** Google style with `Args:` / `Returns:` / `Raises:` sections, as in `build_principal` and `McpServerClient.get_token_for_connection`.
- **Placement:** put new code next to related code or at the end, never at an arbitrary position.

## Comments and docstrings

Enforced on every change (code, tests, docs, commit messages):

1. **Comments earn their place.** Only a non-obvious why, such as a protocol citation (`# RFC 9728`), a security decision, or an intentional omission. Never restate the line below. Default to one sharp line or none.
2. **Docstring format.** One-line description, then `Args`, then `Returns` / `Raises`. No design rationale, that belongs in the PR description.
3. **Plain hyphens only.** No em or en dashes in comments, docstrings, commit messages, or Markdown.
4. **No semicolon clause-splicing.** Split independent clauses into separate sentences.
5. **No internal references.** No ticket numbers, planning-doc paths, internal links, or comparisons with other SDKs.
6. **Helpers stay out of public files.** A private helper goes in `utils/_internal/`. A public helper is a plain-named file in `utils/` and is listed in `__all__`.
