"""Tests for the request context binding and the get_caller_* accessors."""

import pytest

from auth0_ai_mcp import (
    Principal,
    RequestContext,
    UnauthenticatedError,
    bind_request_context,
    get_caller_mcp_client,
    get_caller_principal,
    require_caller_mcp_client,
    require_caller_principal,
)


def _context() -> RequestContext:
    principal = Principal(
        sub="u1", expires_at=9999999999, scopes=[], permissions=None, client_id="client_1", org_id=None
    )
    # OBO is not exercised here, so a plain object stands in for the client.
    return RequestContext(principal=principal, mcp_client=object())  # type: ignore[arg-type]


def test_context_is_set_inside_the_block():
    ctx = _context()
    with bind_request_context(ctx):
        assert get_caller_principal() is ctx.principal
        assert get_caller_mcp_client() is ctx.mcp_client


def test_context_is_reset_after_normal_exit():
    with bind_request_context(_context()):
        pass
    assert get_caller_principal() is None


def test_context_is_reset_after_an_exception():
    with pytest.raises(RuntimeError), bind_request_context(_context()):
        raise RuntimeError("boom")
    assert get_caller_principal() is None


def test_require_caller_principal_returns_principal_inside_a_request():
    ctx = _context()
    with bind_request_context(ctx):
        assert require_caller_principal() is ctx.principal


def test_require_caller_principal_raises_unauthenticated_outside_a_request():
    with pytest.raises(UnauthenticatedError):
        require_caller_principal()


def test_require_caller_mcp_client_returns_client_inside_a_request():
    ctx = _context()
    with bind_request_context(ctx):
        assert require_caller_mcp_client() is ctx.mcp_client


def test_require_caller_mcp_client_raises_unauthenticated_outside_a_request():
    assert get_caller_mcp_client() is None
    with pytest.raises(UnauthenticatedError):
        require_caller_mcp_client()
