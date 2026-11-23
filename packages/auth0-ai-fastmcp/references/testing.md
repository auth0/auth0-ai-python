# Testing

- **Framework:** pytest with pytest-asyncio (versions in the `pyproject.toml` dev group)
- **Location:** `tests/`, one `test_<module>.py` per source module
- **Async mode:** `asyncio_mode = "auto"` in `pyproject.toml`, so `async def test_...` runs without a marker
- **Coverage:** none configured

The suite needs no credentials and makes no network calls.

## Running tests

```bash
poetry run pytest                                   # all unit tests
poetry run pytest tests/test_verifier.py            # one file
poetry run pytest tests/test_middleware.py -k token # filter by name
```

## Conventions

- Tests are module-level `test_<subject>_<condition>` functions. Follow the style of the file you are adding to.
- Cover the failure path as well as the success path. A rejection test must assert that the handler or the next step did not run.
- Placeholders stay obviously synthetic (`user_1`, `https://tenant.example/`). Never paste a real tenant value.
- Name test doubles `Stub...`, never `Fake...`.

## Stubbing and helpers

- `StubMcpClient` in `tests/test_verifier.py` stands in for `McpServerClient`. It returns a `VerifiedToken` with the claims a test chooses, or raises the error a test chooses.
- `tests/test_middleware.py` patches `get_access_token` in the middleware module to control whether a request has a verified token. Its `Recorder` is a `call_next` that records the caller visible while the request runs, so a test can assert on both the bound context and its reset afterwards.
- `tests/test_config.py` patches `create_mcp_client` and `config._Auth0Provider` to stay offline. Where a test needs the real provider, it patches `OIDCConfiguration.get_oidc_configuration` instead.
