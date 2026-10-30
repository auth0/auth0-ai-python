from __future__ import annotations

from starlette.types import Scope


def header_safe(value: str) -> str:
    """Replace anything that could end or escape a quoted header value, or is not printable ASCII."""
    quoted = value.replace('"', "'")
    return "".join(ch if " " <= ch <= "~" and ch != "\\" else " " for ch in quoted)


def bearer_token(scope: Scope) -> str | None:
    """Pull the bearer token from the Authorization header, or None if absent or blank."""
    for name, value in scope.get("headers", []):
        if name == b"authorization":
            parts = value.decode("latin-1").split(" ", 1)
            if len(parts) == 2 and parts[0].lower() == "bearer":
                return parts[1].strip() or None
    return None
