from __future__ import annotations

import importlib.metadata


def package_version(package: str) -> str:
    """Return the installed version of a package, or "unknown" when it is not installed."""
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"
