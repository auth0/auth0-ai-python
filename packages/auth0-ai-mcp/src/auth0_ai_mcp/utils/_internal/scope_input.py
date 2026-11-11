from __future__ import annotations

from auth0_api_python.errors import ConfigurationError


def normalize_scopes(scopes: str | list[str]) -> list[str]:
    """Return the required scopes as a list, rejecting an empty or malformed argument.

    Args:
        scopes: A single scope string or a list of scope strings.

    Returns:
        The required scopes as a list.

    Raises:
        ConfigurationError: If `scopes` is empty, blank, not a string or list, or holds a non-string, blank or whitespace-containing entry.
    """
    required = [scopes] if isinstance(scopes, str) else scopes
    if not isinstance(required, list) or not required:
        raise ConfigurationError("scopes must be a non-empty string or a non-empty list of strings")
    if any(not isinstance(s, str) or not s.strip() for s in required):
        raise ConfigurationError("scopes must not contain blank or non-string entries")
    if any(any(c.isspace() for c in s) for s in required):
        raise ConfigurationError("each scope must be a single value without whitespace, so pass a list for several scopes")
    return list(required)


def normalize_advertised_scopes(scopes: list[str]) -> list[str]:
    """Return the scopes to advertise, where an empty list means none are advertised.

    Args:
        scopes: The scopes to advertise.

    Returns:
        The scopes as a list.

    Raises:
        ConfigurationError: If `scopes` is not a list, or holds a non-string, blank or whitespace-containing entry.
    """
    if not isinstance(scopes, list):
        raise ConfigurationError("scopes_supported must be a list of strings")
    return normalize_scopes(scopes) if scopes else []
