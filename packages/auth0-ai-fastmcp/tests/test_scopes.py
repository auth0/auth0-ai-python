"""Tests for the FastMCP scope checks."""

import logging

import pytest
from auth0_ai_mcp import (
    InsufficientScopeError,
    Principal,
    RequestContext,
    UnauthenticatedError,
    bind_request_context,
)
from auth0_api_python.errors import ConfigurationError
from fastmcp import Client, FastMCP
from fastmcp.exceptions import ToolError

from auth0_ai_fastmcp import require_scopes, with_required_scopes


def _principal(scopes: list[str]) -> Principal:
    return Principal(
        sub="u1",
        expires_at=9999999999,
        scopes=scopes,
        permissions=None,
        client_id="client_1",
        org_id=None,
    )


def _context(scopes: list[str]) -> RequestContext:
    return RequestContext(principal=_principal(scopes), mcp_client=object())  # type: ignore[arg-type]


async def _call(server: FastMCP, name: str = "guarded", arguments: dict | None = None):
    async with Client(server) as client:
        return await client.call_tool(name, arguments or {}, raise_on_error=False)


def test_missing_scope_raises_an_error_that_is_both_insufficient_scope_and_a_tool_error():
    with pytest.raises(InsufficientScopeError) as exc_info:
        require_scopes(_principal(["other"]), "read:x")

    assert isinstance(exc_info.value, ToolError)
    assert exc_info.value.get_status_code() == 403
    assert exc_info.value.get_error_code() == "insufficient_scope"
    assert exc_info.value.log_level == logging.INFO
    assert str(exc_info.value) == "Missing one or more required scopes."


def test_missing_principal_raises_an_error_that_is_both_unauthenticated_and_a_tool_error():
    with pytest.raises(UnauthenticatedError) as exc_info:
        require_scopes(None, "read:x")

    assert isinstance(exc_info.value, ToolError)
    assert exc_info.value.get_status_code() == 401
    assert exc_info.value.log_level == logging.INFO


def test_granted_scope_passes():
    require_scopes(_principal(["read:x"]), "read:x")


def test_sync_handler_is_rejected_at_decoration_time():
    with pytest.raises(ConfigurationError):

        @with_required_scopes("read:x")
        def guarded() -> str:
            return "body"


def test_bad_scope_argument_still_raises_configuration_error():
    with pytest.raises(ConfigurationError):
        require_scopes(_principal(["read:x"]), "read:x write:y")
    with pytest.raises(ConfigurationError):
        with_required_scopes("")


@pytest.mark.parametrize("mask_error_details", [False, True])
async def test_denied_tool_shows_the_reason_to_the_client(mask_error_details):
    server = FastMCP("test", mask_error_details=mask_error_details)

    @server.tool
    @with_required_scopes("read:x")
    async def guarded() -> str:
        return "body"

    with bind_request_context(_context(["other"])):
        result = await _call(server)

    assert result.is_error
    assert result.content[0].text == "Missing one or more required scopes."


async def test_tool_without_a_caller_shows_the_reason_to_the_client():
    server = FastMCP("test")

    @server.tool
    @with_required_scopes("read:x")
    async def guarded() -> str:
        return "body"

    result = await _call(server)

    assert result.is_error
    assert result.content[0].text == "No principal in the current request context."


async def test_denied_tool_is_logged_without_a_traceback(caplog):
    server = FastMCP("test")

    @server.tool
    @with_required_scopes("read:x")
    async def guarded() -> str:
        return "body"

    with caplog.at_level(logging.INFO), bind_request_context(_context(["other"])):
        await _call(server)

    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert not [r for r in caplog.records if r.exc_info]


async def test_decorator_placed_above_the_tool_registration_does_not_guard_the_tool():
    server = FastMCP("test")

    @with_required_scopes("read:x")
    @server.tool
    async def unguarded() -> str:
        return "body"

    with bind_request_context(_context(["other"])):
        result = await _call(server, name="unguarded")

    assert not result.is_error


async def test_granted_tool_runs_and_keeps_its_parameters():
    server = FastMCP("test")

    @server.tool
    @with_required_scopes("read:x")
    async def guarded(city: str) -> str:
        """Look up a city."""
        return f"weather in {city}"

    tool = (await server.list_tools())[0]
    with bind_request_context(_context(["read:x"])):
        result = await _call(server, arguments={"city": "Oslo"})

    assert list(tool.parameters["properties"]) == ["city"]
    assert tool.description == "Look up a city."
    assert not result.is_error
    assert result.content[0].text == "weather in Oslo"


async def test_denied_resource_shows_the_reason_to_the_client():
    server = FastMCP("test")

    @server.resource("store://catalog")
    @with_required_scopes("read:x")
    async def catalog() -> str:
        return "body"

    with bind_request_context(_context(["other"])):
        async with Client(server) as client:
            with pytest.raises(Exception, match="Missing one or more required scopes."):
                await client.read_resource("store://catalog")
