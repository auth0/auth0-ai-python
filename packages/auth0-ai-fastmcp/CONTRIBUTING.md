# Contribution

Please read [Auth0's contribution guidelines](https://github.com/auth0/open-source-template/blob/master/GENERAL-CONTRIBUTING.md).

## Environment setup

- Python 3.10 or newer and Poetry
- Run `poetry install` to install dependencies
- Follow the local development steps below to get started

## Local development

- `poetry install`: install dependencies
- `poetry run pytest`: run unit tests
- `poetry run ruff check .`: check code style and lint errors
- `poetry build`: build the package

## Testing

### Adding tests

Every change should be accompanied by a test.

### Running tests

Run unit tests and the linter before opening a PR:

```bash
poetry run pytest
poetry run ruff check .
```