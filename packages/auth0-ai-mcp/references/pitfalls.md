# Common Pitfalls

1. **Do not run `ruff format .`.** CI runs only `ruff check .`. The tree is not ruff-formatted (`ruff format --check .` reports files that would be reformatted), so a repo-wide format produces a large unrelated diff. Match surrounding formatting by hand.
2. **Python 3.10 floor.** CI tests 3.10 to 3.12 and `.ruff.toml` targets `py310`. `X | Y` unions and `match` are fine. Syntax newer than 3.10 is not.
3. **Async tests need no marker.** `asyncio_mode = "auto"` is set, so a bare `async def test_...` runs. Adding `@pytest.mark.asyncio` is harmless but unneeded.
4. **Only `PLC0415` is a preview rule.** `.ruff.toml` turns on `preview` with `explicit-preview-rules`, so no other preview rule applies. An import inside a function fails lint, move it to the top or under `TYPE_CHECKING`.
5. **The core SDK is pinned by git SHA.** `auth0-api-python` in `pyproject.toml` points at a commit, not a release. Do not bump it casually, and note that PyPI rejects git-URL dependencies, so a release needs the pin replaced by a published version first.
6. **Caching and stores are not here.** `token_store` and `scope_matching` are forwarded to the core `ApiClient`, so a caching bug is usually fixed in the core SDK. This package only passes the options through.
7. **The middleware is not in `__all__`.** Import it as `from auth0_ai_mcp.middleware import Auth0AsgiMiddleware`. A new public symbol in `middleware.py` follows the same path rather than being added to `__init__.py`.
8. **Accessors return `None` outside a request.** `get_caller_principal()` and `get_caller_mcp_client()` return `None` when no context is set, while `require_caller_mcp_client()` raises `UnauthenticatedError`. Tests that call tool code directly must set the context first.
9. **Examples read environment variables at import.** `examples/b2b_ecommerce/tools.py` indexes `os.environ` for each audience at module level, so importing it without the variables raises `KeyError`. `ruff check .` still lints it.
10. **No separate requirements file.** Dependencies live only in `pyproject.toml` and `poetry.lock`, and the Snyk scan reads them from there.
11. **Stale local venvs.** A hand-made venv in the working tree (anything other than Poetry's) may not have the package or dev dependencies installed. Use `poetry install` then `poetry run ...` so you test the same environment CI does.
