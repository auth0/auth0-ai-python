"""Tests for require_scopes and the with_required_scopes decorator."""

import inspect

import pytest
from auth0_api_python.errors import ConfigurationError

from auth0_ai_mcp import Principal
from auth0_ai_mcp.errors import InsufficientScopeError, UnauthenticatedError
from auth0_ai_mcp.request_context import RequestContext, reset_request_context, set_request_context
from auth0_ai_mcp.scopes import require_scopes, with_required_scopes


def _principal(scopes: list[str]) -> Principal:
    return Principal(
        sub="u1",
        expires_at=9999999999,
        scopes=scopes,
        permissions=None,
        client_id="client_1",
        org_id=None,
    )


def _make_context(principal: Principal) -> RequestContext:
    # mcp_client is required by the dataclass. Pass a plain object since OBO is not tested here.
    return RequestContext(principal=principal, mcp_client=object())  # type: ignore[arg-type]


def test_passes_when_principal_has_all_scopes():
    require_scopes(_principal(["read:x", "write:y"]), ["read:x", "write:y"])


def test_passes_with_superset_of_required_scopes():
    require_scopes(_principal(["read:x", "write:y", "admin"]), ["read:x"])


def test_single_string_is_one_scope():
    require_scopes(_principal(["read:x"]), "read:x")


@pytest.mark.parametrize("required", ["write:y", ["read:x", "write:y"]])
def test_raises_insufficient_scope_when_any_required_scope_is_missing(required):
    with pytest.raises(InsufficientScopeError) as exc_info:
        require_scopes(_principal(["read:x"]), required)

    assert exc_info.value.get_status_code() == 403
    assert exc_info.value.get_error_code() == "insufficient_scope"


def test_scope_held_only_as_a_permission_does_not_satisfy_the_check():
    principal = Principal(
        sub="u1", expires_at=9999999999, scopes=[], permissions=["read:x"], client_id="client_1", org_id=None
    )

    with pytest.raises(InsufficientScopeError):
        require_scopes(principal, "read:x")


def test_insufficient_scope_message_does_not_leak_scope():
    with pytest.raises(InsufficientScopeError) as exc_info:
        require_scopes(_principal(["read:x"]), ["read:x", "write:y"])
    assert "write:y" not in str(exc_info.value)


def test_raises_unauthenticated_when_principal_is_none():
    with pytest.raises(UnauthenticatedError) as exc_info:
        require_scopes(None, "read:x")

    assert exc_info.value.get_status_code() == 401
    assert exc_info.value.get_error_code() == "invalid_token"


@pytest.mark.parametrize("scopes", [[], "", "   ", ["read:x", ""], ["read:x", " "], ["read:x", 1], None, ("read:x",)])
def test_rejects_empty_or_malformed_scopes(scopes: object):
    with pytest.raises(ConfigurationError):
        require_scopes(_principal(["read:x"]), scopes)  # type: ignore[arg-type]


@pytest.mark.parametrize(("required", "held"), [("read:x", ["read:x"]), (["read:x", "write:y"], ["read:x", "write:y"])])
async def test_handler_runs_when_principal_has_every_required_scope(required, held):
    ctx = _make_context(_principal(held))
    token = set_request_context(ctx)
    try:
        @with_required_scopes(required)
        async def handler() -> str:
            return "ok"

        result = await handler()
        assert result == "ok"
    finally:
        reset_request_context(token)


async def test_args_and_kwargs_pass_through():
    ctx = _make_context(_principal(["read:x"]))
    token = set_request_context(ctx)
    try:
        @with_required_scopes("read:x")
        async def handler(a: int, *, b: str) -> tuple:
            return (a, b)

        assert await handler(1, b="hello") == (1, "hello")
    finally:
        reset_request_context(token)


async def test_raises_insufficient_scope_and_inner_body_does_not_run():
    ctx = _make_context(_principal(["read:x"]))
    token = set_request_context(ctx)
    try:
        inner_ran = False

        @with_required_scopes("write:y")
        async def handler() -> None:
            nonlocal inner_ran
            inner_ran = True

        with pytest.raises(InsufficientScopeError):
            await handler()

        # The guard must have fired before the body. inner_ran must still be False.
        assert inner_ran is False
    finally:
        reset_request_context(token)


@pytest.mark.parametrize("scopes", [[], "", ["read:x", ""], ["read:x", 1]])
def test_rejects_empty_or_malformed_scopes_at_decoration_time(scopes: object):
    with pytest.raises(ConfigurationError):
        with_required_scopes(scopes)  # type: ignore[arg-type]


async def test_raises_unauthenticated_when_no_context_is_set():
    # Do not set any context. The contextvar defaults to None.
    @with_required_scopes("read:x")
    async def handler() -> None:
        pass  # pragma: no cover

    with pytest.raises(UnauthenticatedError):
        await handler()


def test_decorated_handler_keeps_its_name_doc_and_signature():
    @with_required_scopes("read:x")
    async def handler(a: int, *, b: str = "x") -> str:
        """Handler doc."""
        return b

    assert handler.__name__ == "handler"
    assert handler.__doc__ == "Handler doc."
    assert list(inspect.signature(handler).parameters) == ["a", "b"]
