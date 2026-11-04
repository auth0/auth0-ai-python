# Git Workflow

## Branch naming

`feat/<topic>`, `fix/<topic>`, `docs/<topic>`, `chore/<topic>`. Release branches are prefixed with the package name, `release/auth0-ai-fastmcp-<version>`. Dependabot opens `dependabot/...` branches. Base branch is `main`.

## Commit messages

Conventional Commits prefixes (`feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`), lowercase subject, no trailing period. Example: `fix: return no access token when the scope claim is missing`. No commit linter is configured, so match the prefix style by hand.

## Pull requests

`.github/PULL_REQUEST_TEMPLATE.md` (at the repository root) sections:

- **Changes:** what and why, classes and methods added, changed, or deprecated, and a usage summary for public API changes
- **References:** supporting links
- **Testing:** how to test, with checkboxes for unit coverage, integration coverage, and latest-platform testing
- **Checklist:** Auth0 contribution guidelines and Code of Conduct

The template asks for a method-level inventory, so write the PR body from the diff of the public surface (`__init__.py` `__all__`, `Auth0FastMCP`, `Auth0FastMCPOptions`, `Auth0TokenVerifier`, `Auth0ContextMiddleware`), not from a summary of intent.

## CI

Pull requests run `pytest -v` and `ruff check .` on Python 3.10 to 3.14, plus CodeQL, a Snyk scan with suppressions in `.snyk`, and OpenSSF Scorecard. `ruff format` is not a check, so reformatting untouched files creates noise CI won't flag but reviewers will.

## Releases

`.version` is the version source. `.shiprc` keeps `pyproject.toml` in step with it. Releases are cut by the publish workflow, not by an agent editing version files. `CHANGELOG.md` is written as part of that flow, so a feature commit does not touch it.
