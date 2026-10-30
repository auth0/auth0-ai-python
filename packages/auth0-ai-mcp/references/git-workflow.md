# Git Workflow

## Branch naming

`feat/<topic>`, `fix/<topic>`, `docs/<topic>`, `chore/<topic>`. Release branches are prefixed with the package name, `release/auth0-ai-mcp-<version>`. Dependabot opens `dependabot/...` branches. Base branch is `main`.

## Commit messages

Conventional Commits prefixes (`feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`), lowercase subject, no trailing period. Example: `fix: reject exchanged tokens that miss requested scopes`. No commit linter is configured, so match the prefix style by hand.

## Pull requests

`.github/PULL_REQUEST_TEMPLATE.md` (at the repository root) sections:

- **Changes:** what and why, classes and methods added, changed, or deprecated, and a usage summary for public API changes
- **References:** supporting links
- **Testing:** how to test, with checkboxes for unit coverage, integration coverage, and latest-platform testing
- **Checklist:** Auth0 contribution guidelines and Code of Conduct

The template asks for a method-level inventory, so write the PR body from the diff of the public surface (`__init__.py` `__all__`, `McpServerClient`, `RequestScopedMcpClient`, `errors.py`), not from a summary of intent.

`CODEOWNERS` assigns every path to `@auth0/project-dx-sdks-engineer-codeowner`.

## CI workflows

From `.github/workflows/`. Which of these are required status checks is set in branch protection, not in the repo.

- **Build and Test** (`test.yml`): a package matrix with Python 3.10 to 3.12, running `pytest -v` and `ruff check .` on PR, merge group, and push to `main`
- **CodeQL** (`codeql.yml`): on PR, merge group, push to `main`, and a weekly schedule
- **SCA** (`sca_scan.yml`): Snyk scan on push and PR to `main`, with suppressions in `.snyk`
- **Scorecard** (`scorecard.yml`): OpenSSF Scorecard checks
- **Publish** (`publish.yml`): manual dispatch, see Releases

`ruff format` is not a check. Reformatting untouched files creates noise CI won't flag but reviewers will.

## Releases

`.version` is the version source. `.shiprc` keeps `pyproject.toml` in step with it. Releases are cut by `publish.yml` (manual dispatch with a `package` input, gated on the RL scan), not by an agent editing version files. `CHANGELOG.md` is written as part of that flow, so a feature commit does not touch it.
