"""Tests for Auth0TokenVerifier."""

import base64
import json
import logging

import pytest
from auth0_ai_mcp import (
    AuthServerUnavailableError,
    VerifiedToken,
    VerifyAccessTokenError,
    create_mcp_client,
)

from auth0_ai_fastmcp.verifier import Auth0TokenVerifier


class StubMcpClient:
    def __init__(self, claims=None, error=None):
        self._claims = claims
        self._error = error

    async def verify_access_token(self, access_token):
        if self._error:
            raise self._error
        return VerifiedToken(access_token=access_token, claims=self._claims)


async def test_valid_token_returns_access_token():
    claims = {"sub": "user1", "scope": "a b", "client_id": "cid", "exp": 123}

    result = await Auth0TokenVerifier(StubMcpClient(claims)).verify_token("tok")

    assert result is not None
    assert result.token == "tok"
    assert result.client_id == "cid"
    assert result.scopes == ["a", "b"]
    assert result.subject == "user1"
    assert result.expires_at == 123
    assert result.claims == claims


async def test_fractional_exp_is_accepted():
    claims = {"sub": "u", "scope": "", "azp": "app1", "exp": 1700000000.5}

    result = await Auth0TokenVerifier(StubMcpClient(claims)).verify_token("tok")

    assert result is not None
    assert result.expires_at == 1700000000


@pytest.mark.parametrize(
    "claims",
    [
        {},
        {"sub": "u", "azp": "app1"},
    ],
)
async def test_token_without_usable_caller_claims_returns_none(claims):
    assert await Auth0TokenVerifier(StubMcpClient(claims)).verify_token("tok") is None


async def test_a_rejected_token_logs_the_reason_and_never_the_token(caplog):
    client = StubMcpClient(error=VerifyAccessTokenError("invalid token"))
    token = "secret-tok-123456"

    with caplog.at_level(logging.WARNING, logger="auth0_ai_fastmcp.verifier"):
        await Auth0TokenVerifier(client).verify_token(token)

    assert "VerifyAccessTokenError: 'invalid token'" in caplog.text
    assert token[:8] not in caplog.text
    assert token[-6:] not in caplog.text


async def test_a_rejection_reason_with_a_line_break_is_escaped_in_the_log(caplog):
    client = StubMcpClient(error=VerifyAccessTokenError("bad\nINJECTED line"))

    with caplog.at_level(logging.WARNING, logger="auth0_ai_fastmcp.verifier"):
        await Auth0TokenVerifier(client).verify_token("tok")

    assert "bad\\nINJECTED line" in caplog.text
    assert "bad\nINJECTED" not in caplog.text


async def test_rejected_token_returns_none():
    client = StubMcpClient(error=VerifyAccessTokenError("invalid token"))

    assert await Auth0TokenVerifier(client).verify_token("bad") is None


def _unsigned_jwt(header, payload):
    def encode(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()

    return f"{encode(header)}.{encode(payload)}.signature"


@pytest.mark.parametrize(
    "header, payload",
    [
        ([1], {}),
        ({"alg": "RS256", "kid": "k"}, [1]),
    ],
)
async def test_a_token_with_a_non_object_segment_returns_none_for_a_real_client(header, payload):
    client = create_mcp_client("tenant.auth0.com", "https://api.example.com/mcp")

    assert await Auth0TokenVerifier(client).verify_token(_unsigned_jwt(header, payload)) is None


@pytest.mark.parametrize("token", ["", "   "])
async def test_blank_token_returns_none_without_calling_the_client(token):
    client = StubMcpClient(error=AssertionError("the client must not be called"))

    assert await Auth0TokenVerifier(client).verify_token(token) is None


async def test_unreachable_auth_server_is_not_reported_as_an_invalid_token(caplog):
    client = StubMcpClient(error=AuthServerUnavailableError("Failed to fetch JWKS"))
    token = "secret-tok-123456"

    with caplog.at_level(logging.DEBUG, logger="auth0_ai_fastmcp.verifier"):
        with pytest.raises(AuthServerUnavailableError):
            await Auth0TokenVerifier(client).verify_token(token)

    assert token not in caplog.text


async def test_other_client_errors_propagate_instead_of_becoming_none():
    client = StubMcpClient(error=RuntimeError("misconfigured"))

    with pytest.raises(RuntimeError):
        await Auth0TokenVerifier(client).verify_token("tok")
