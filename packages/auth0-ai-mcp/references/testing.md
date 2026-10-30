# Testing

- **Framework:** pytest with pytest-asyncio (versions in the `pyproject.toml` dev group)
- **Location:** `tests/`, one `test_<module>.py` per source module
- **Async mode:** `asyncio_mode = "auto"` in `pyproject.toml`, so `async def test_...` runs without a marker
- **Coverage:** none configured

The suite needs no credentials and makes no network calls.

## Running tests

```bash
poetry run pytest                                   # all unit tests
poetry run pytest tests/test_principal.py           # one file
poetry run pytest tests/test_client.py -k downscoped  # filter by name
```

## Conventions

- `test_client.py` and `test_principal.py` use module-level `test_<subject>_<condition>` functions. `test_scopes.py` groups tests in `TestRequireScopes` and `TestWithRequiredScopes`. Follow the style of the file you are adding to.
- Assert on the error type with `pytest.raises(...)`. Where a test cares about the contract, assert `get_error_code()` and `get_status_code()` rather than message text.
- Messages that must stay generic have their own test, for example `test_insufficient_scope_message_does_not_leak_scope` and `test_downscoped_error_message_does_not_leak_scopes`. Add one when a new error could carry scope or token detail.
- Placeholders stay obviously synthetic (`user_1`, `https://tenant.example/`). Never paste a real tenant value.
- Name test doubles `Stub...`, never `Fake...`.

## Stubbing and helpers

- `StubApiClient` in `tests/test_client.py` stands in for the core `ApiClient`, records the exchange calls it receives, and lets a test choose the granted scope, the expiry, or an error to raise. Reuse it, and extend it when a new core method is wrapped.
- `_verified(...)` builds a `VerifiedToken` from synthetic claims and `_jwt(...)` builds an unsigned JWT that carries them.
- Behavior tests wrap the stub directly with `McpServerClient(StubApiClient(...))`. Constructor wiring tests call `create_mcp_client(...)` and inspect the `ApiClientOptions` on `client._api.options`.
- Tests that need a caller build a `RequestContext` and run the code inside `with bind_request_context(...):`, which resets the context on exit so state does not leak between tests (see `tests/test_request_context.py`).

## Middleware tests

`tests/test_middleware.py` drives `Auth0AsgiMiddleware` as a plain ASGI callable with a `StubApiClient` (returns claims or raises) and a `StubApp` (records whether it ran and which caller it saw). Reuse `_call` to collect the sent messages. Cover both the `401` path and the app-ran path when changing the middleware. Middleware behavior is covered in `tests/test_middleware.py` and request context in `tests/test_request_context.py`.
