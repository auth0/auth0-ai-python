# Commands

Run these from the `auth0-ai-mcp` directory. They match `.github/workflows/test.yml` (Poetry 2.2.1, Python 3.10 to 3.12) and `CONTRIBUTING.md`.

```bash
# Install dependencies and the package (CI runs both steps)
poetry install --no-interaction --no-root
poetry install --no-interaction

# Run all unit tests (CI runs pytest -v)
poetry run pytest

# One file, or filter by name
poetry run pytest tests/test_scopes.py
poetry run pytest tests/test_client.py -k downscoped

# Lint (CI-enforced)
poetry run ruff check .

# Auto-fix lint issues (review the diff, keep it scoped to your change)
poetry run ruff check . --fix

# Show formatting state only (not a CI gate, never apply repo-wide)
poetry run ruff format --check .

# Build sdist and wheel into dist/
poetry build

# Clean generated artifacts
rm -rf dist/ .coverage coverage.xml .pytest_cache .ruff_cache
find . -path ./.venv\* -prune -o -name __pycache__ -type d -prune -exec rm -rf {} +
```

## Not available here

- **No typecheck command.** mypy and pyright are not in `pyproject.toml` and no CI step runs them.
- **No coverage tooling.** `pytest-cov` is not a dev dependency and no threshold is configured.
- **No integration tier.** The suite stubs the core client and needs no Auth0 tenant. The example server in `examples/b2b_ecommerce` is the only thing that talks to a real tenant, and it is run by hand.

`publish.yml` (manual `workflow_dispatch`) builds, runs the RL scanner, and publishes to PyPI. Agents do not run releases.
