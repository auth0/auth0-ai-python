import time

import pytest
from auth0_api_python.errors import VerifyAccessTokenError

from auth0_ai_mcp import Principal
from auth0_ai_mcp.principal import build_principal


def test_build_principal_with_all_claims_present():
    claims = {
        "sub": "auth0|user123",
        "exp": int(time.time()) + 3600,
        "scope": "calendar:read calendar:write",
        "permissions": ["calendar:read", "calendar:write"],
        "client_id": "my_client_id",
        "org_id": "org_abc123",
    }

    principal = build_principal(claims)

    assert principal == Principal(
        sub="auth0|user123",
        expires_at=claims["exp"],
        scopes=["calendar:read", "calendar:write"],
        permissions=["calendar:read", "calendar:write"],
        client_id="my_client_id",
        org_id="org_abc123",
    )


def test_build_principal_permissions_present_but_empty():
    claims = {
        "sub": "auth0|user123",
        "exp": int(time.time()) + 3600,
        "azp": "spa_client_id",
        "permissions": [],
    }

    principal = build_principal(claims)

    assert principal.permissions == []


def test_build_principal_missing_both_org_id_and_permissions():
    claims = {
        "sub": "auth0|user123",
        "exp": int(time.time()) + 3600,
        "azp": "spa_client_id",
    }

    principal = build_principal(claims)

    assert principal.org_id is None
    assert principal.permissions is None


def test_build_principal_missing_scope_claim_yields_empty_list():
    claims = {
        "sub": "auth0|user123",
        "exp": int(time.time()) + 3600,
        "azp": "spa_client_id",
    }

    principal = build_principal(claims)

    assert principal.scopes == []


_ABSENT = object()


def _claims(**overrides):
    claims = {"sub": "auth0|user123", "exp": int(time.time()) + 3600, "azp": "spa_client_id"}
    claims.update(overrides)
    return {k: v for k, v in claims.items() if v is not _ABSENT}


@pytest.mark.parametrize("sub", [_ABSENT, " ", "\t\n", 123, None])
def test_build_principal_rejects_blank_or_non_string_sub(sub):
    with pytest.raises(VerifyAccessTokenError, match="sub"):
        build_principal(_claims(sub=sub))


def test_build_principal_prefers_azp_over_client_id():
    principal = build_principal(_claims(azp="azp_value", client_id="client_id_value"))

    assert principal.client_id == "azp_value"


@pytest.mark.parametrize("azp", [_ABSENT, None, "", "  ", 42])
def test_build_principal_falls_back_to_client_id_when_azp_is_unusable(azp):
    principal = build_principal(_claims(azp=azp, client_id="client_id_value"))

    assert principal.client_id == "client_id_value"


@pytest.mark.parametrize(
    ("azp", "client_id"),
    [(_ABSENT, _ABSENT), (None, None), ("  ", "  "), (42, 42), ("", ["c"])],
)
def test_build_principal_rejects_claims_without_a_usable_client(azp, client_id):
    with pytest.raises(VerifyAccessTokenError, match="client_id"):
        build_principal(_claims(azp=azp, client_id=client_id))


@pytest.mark.parametrize("exp", [_ABSENT, None, "4102444800", True, False, float("nan"), float("inf"), [1]])
def test_build_principal_rejects_missing_or_non_numeric_exp(exp):
    with pytest.raises(VerifyAccessTokenError, match="exp"):
        build_principal(_claims(exp=exp))


def test_build_principal_accepts_a_float_exp():
    assert build_principal(_claims(exp=4102444800.5)).expires_at == 4102444800.5


@pytest.mark.parametrize("permissions", ["read:x", {"read:x": True}, ["read:x", 1], [None]])
def test_build_principal_rejects_permissions_that_are_not_a_list_of_strings(permissions):
    with pytest.raises(VerifyAccessTokenError, match="permissions"):
        build_principal(_claims(permissions=permissions))


def test_build_principal_treats_null_permissions_as_absent():
    assert build_principal(_claims(permissions=None)).permissions is None


@pytest.mark.parametrize("org_id", [123, ["org_abc"], {"id": "org_abc"}, True])
def test_build_principal_rejects_non_string_org_id(org_id):
    with pytest.raises(VerifyAccessTokenError, match="org_id"):
        build_principal(_claims(org_id=org_id))


@pytest.mark.parametrize("scope", [["read:x"], 123, {"read:x": True}])
def test_build_principal_non_string_scope_yields_empty_list(scope):
    assert build_principal(_claims(scope=scope)).scopes == []
