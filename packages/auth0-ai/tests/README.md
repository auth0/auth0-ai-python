# Testing Guide for auth0-ai

This package uses **pytest** for testing.

## Running Tests

```bash
# Run all tests
poetry run pytest

# Run with verbose output
poetry run pytest -v

# Run a specific test file
poetry run pytest tests/test_token_vault_authorizer.py

# Run a specific test
poetry run pytest tests/test_token_vault_authorizer.py::TestTokenVaultAuthorizerParams::test_initialization_with_refresh_token

# Run tests matching a pattern
poetry run pytest -k "refresh_token"
```

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Pytest Fixtures](https://docs.pytest.org/en/stable/fixture.html)
- [Pytest Parametrize](https://docs.pytest.org/en/stable/parametrize.html)
