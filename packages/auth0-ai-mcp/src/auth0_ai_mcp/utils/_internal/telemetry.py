from __future__ import annotations

import importlib.metadata

_PACKAGE_NAME = "auth0-ai-mcp"


def _package_version() -> str:
    try:
        return importlib.metadata.version(_PACKAGE_NAME)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def build_client_info(wrapper: dict | None = None) -> dict:
    """Build the client_info passed to the core SDK, reporting this package or the wrapper built on it."""
    if wrapper is None:
        return {"name": _PACKAGE_NAME, "version": _package_version()}
    if not isinstance(wrapper, dict) or not isinstance(wrapper.get("env", {}), dict):
        return wrapper
    return {**wrapper, "env": {**wrapper.get("env", {}), _PACKAGE_NAME: _package_version()}}
