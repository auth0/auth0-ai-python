# Common Pitfalls

1. **Do not run `ruff format .`.** CI runs only `ruff check .`. Match surrounding formatting by hand.
2. **Python 3.10 floor.** `.ruff.toml` targets `py310`. `X | Y` unions and `match` are fine. Syntax newer than 3.10 is not.
3. **Async tests need no marker.** `asyncio_mode = "auto"` is set, so a bare `async def test_...` runs.
4. **Only `PLC0415` is a preview rule.** An import inside a function fails lint, move it to the top or under `TYPE_CHECKING`.
5. **`required_scopes` must reach the verifier.** FastMCP reads the required scopes from the token verifier. `Auth0MCPProvider` only forwards them to its own default verifier, so with a custom verifier they are dropped unless `Auth0TokenVerifier` passes them to `TokenVerifier.__init__`.
6. **`audience` must equal the advertised resource.** `resource_url` is the base URL and FastMCP appends the MCP path (default `/mcp`). `audience` defaults to that value. A server mounted at another path needs `mcp_path` set to match, otherwise `http_app` or `run` raises `ConfigurationError` because every token would fail the audience check.
7. **`initialize`, `ping` and `server/discover` carry no caller.** `Auth0ContextMiddleware` lets them through without a token. Over HTTP, FastMCP's own auth still answers a request with no token with a `401` before the middleware runs. Every other request without a verified token is rejected, including one from an in-memory `Client(mcp)` or stdio, so test tools over HTTP with a real token.
8. **Hooks run in a fixed order.** For `tools/call`, `resources/read`, `prompts/get`, and the list requests, FastMCP runs `on_message`, then `on_request`, then the typed hook. The context is bound in `on_request`, so it is visible to every typed hook that runs after it and to the handler. A middleware registered earlier than `Auth0ContextMiddleware` does not see the caller.
9. **The caller accessors return `None` outside a request.** Tests that call tool code directly must bind a `RequestContext` first.
10. **The provider constructor makes a network call.** `Auth0MCPProvider` performs OIDC discovery when it is built, so `Auth0FastMCP` builds it once and tests patch it.
11. **Examples read environment variables at import.** Importing `examples/b2b_ecommerce/tools.py` without the variables raises `KeyError`. `ruff check .` still lints it.
12. **No separate requirements file.** Dependencies live only in `pyproject.toml` and `poetry.lock`.
13. **Stale local venvs.** Use `poetry install` then `poetry run ...` so you test the same environment CI does.
