from __future__ import annotations

import time

from auth0_api_python import TokenSet
from auth0_api_python.errors import BaseAuthError

from ...errors import DownscopedTokenError


def token_set(result: dict) -> TokenSet:
    """Build the same `TokenSet` shape for every flow, adding `granted_scopes` when the response has a scope."""
    tokens: TokenSet = {
        "access_token": result["access_token"],
        "expires_at": result["expires_at"],
    }
    if result.get("scope"):
        tokens["granted_scopes"] = result["scope"]
    return tokens


def reject_if_expired(result: dict, error: type[BaseAuthError]) -> None:
    """Raise `error` if the returned token has no usable `expires_at` or has already expired."""
    expires_at = result.get("expires_at")
    if isinstance(expires_at, bool) or not isinstance(expires_at, (int, float)) or expires_at <= time.time():
        raise error("The exchanged token is already expired.")


def reject_if_downscoped(requested: str | None, result: dict) -> None:
    """Raise if the exchange granted fewer scopes than were requested.

    An absent `scope` response field means the grant matched the request (RFC 6749
    section 5.1), so only a present field is diffed. The message stays generic on
    purpose and does not name the missing scopes.
    """
    if not requested or "scope" not in result:
        return
    granted = {s for s in (result["scope"] or "").split() if s}
    missing = {s for s in requested.split() if s} - granted
    if missing:
        raise DownscopedTokenError(
            "Exchanged token did not include all requested scopes."
        )
