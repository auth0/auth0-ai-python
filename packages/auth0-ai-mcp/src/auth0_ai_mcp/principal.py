"""
Verified caller identity, normalized from access token claims.
"""

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from auth0_api_python.errors import VerifyAccessTokenError


@dataclass
class Principal:
    """
    Normalized caller identity built from a verified access token's claims.

    Attributes:
        sub: The subject claim identifying the caller.
        expires_at: Unix epoch seconds the token expires, from the "exp" claim.
        scopes: Parsed from the space-separated "scope" claim. Empty list if absent.
        permissions: From the "permissions" claim. None when the claim is absent from
            the token (RBAC not enabled on the API), a list (possibly empty) when present.
        client_id: From the "azp" claim, falling back to "client_id". Always set, because a token with neither is rejected.
        org_id: From the "org_id" claim. None when the token carries no Organization.
    """

    sub: str
    expires_at: int | float
    scopes: list[str]
    permissions: list[str] | None
    client_id: str
    org_id: str | None


def build_principal(claims: Mapping[str, Any]) -> Principal:
    """
    Build a Principal from a verified access token's claims.

    Args:
        claims: The claims dict returned by ApiClient.verify_access_token. This must be
            the already-verified claims, never a raw token or unverified input.

    Returns:
        A Principal normalizing the claims tool code needs.

    Raises:
        VerifyAccessTokenError: If "sub" is missing or blank, "exp" is missing or not a finite number, neither "azp" nor "client_id" is a non-blank string, "permissions" is not a list of strings, or "org_id" is not a string.
    """
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub.strip():
        raise VerifyAccessTokenError("Access token is missing the required 'sub' claim")

    exp = claims.get("exp")
    if isinstance(exp, bool) or not isinstance(exp, (int, float)) or not math.isfinite(exp):
        raise VerifyAccessTokenError("Access token has a missing or invalid 'exp' claim")

    client_id = next(
        (
            value
            for value in (claims.get("azp"), claims.get("client_id"))
            if isinstance(value, str) and value.strip()
        ),
        None,
    )
    if client_id is None:
        raise VerifyAccessTokenError("Access token is missing the 'azp' or 'client_id' claim")

    permissions = claims.get("permissions")
    if permissions is not None and (
        not isinstance(permissions, list) or not all(isinstance(p, str) for p in permissions)
    ):
        raise VerifyAccessTokenError("Access token has an invalid 'permissions' claim")

    org_id = claims.get("org_id")
    if org_id is not None and not isinstance(org_id, str):
        raise VerifyAccessTokenError("Access token has an invalid 'org_id' claim")

    scope = claims.get("scope") or ""
    scopes = scope.split() if isinstance(scope, str) else []

    return Principal(
        sub=sub,
        expires_at=exp,
        scopes=scopes,
        permissions=permissions,
        client_id=client_id,
        org_id=org_id,
    )
