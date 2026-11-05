"""Tests for Auth0ContextMiddleware."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from auth0_ai_mcp import (
    ApiError,
    DownscopedTokenError,
    UnauthenticatedError,
    VerifyAccessTokenError,
    get_caller_mcp_client,
    get_caller_principal,
)
from fastmcp import Client, FastMCP
from fastmcp.exceptions import PromptError, ResourceError, ToolError
from fastmcp.server.auth.auth import AccessToken

from auth0_ai_fastmcp.middleware import Auth0ContextMiddleware

_CLAIMS = {"sub": "u", "azp": "cid", "scope": "x", "exp": 9999}


class StubMcpClient:
    def __init__(self):
        self.bound = []

    def with_token(self, verified, principal):
        self.bound.append((verified, principal))
        return f"client-for-{principal.sub}"


def _access_token(claims=None) -> AccessToken:
    return AccessToken(
        token="tok", client_id="cid", scopes=["x"], claims=_CLAIMS if claims is None else claims
    )


def _context(method="tools/call"):
    return SimpleNamespace(method=method)


def _patch_token(access_token):
    return patch("auth0_ai_fastmcp.middleware.get_access_token", return_value=access_token)


class Recorder:
    """A call_next that records the caller visible while the request runs."""

    def __init__(self, error=None):
        self.error = error
        self.seen = None

    async def __call__(self, context):
        self.seen = (get_caller_principal(), get_caller_mcp_client())
        if self.error:
            raise self.error
        return "result"


async def test_caller_is_visible_to_the_handler():
    stub = StubMcpClient()
    call_next = Recorder()

    with _patch_token(_access_token()):
        result = await Auth0ContextMiddleware(stub).on_request(_context(), call_next)

    principal, client = call_next.seen
    assert result == "result"
    assert principal.sub == "u"
    assert principal.client_id == "cid"
    assert client == "client-for-u"
    verified, _ = stub.bound[0]
    assert verified.access_token == "tok"
    assert verified.claims == _CLAIMS


async def test_context_is_cleared_after_the_request():
    with _patch_token(_access_token()):
        await Auth0ContextMiddleware(StubMcpClient()).on_request(_context(), Recorder())

    assert get_caller_principal() is None


async def test_context_is_cleared_when_the_handler_raises():
    call_next = Recorder(error=RuntimeError("boom"))

    with _patch_token(_access_token()):
        with pytest.raises(RuntimeError):
            await Auth0ContextMiddleware(StubMcpClient()).on_request(_context(), call_next)

    assert get_caller_principal() is None


@pytest.mark.parametrize("method", ["tools/call", "resources/read", "prompts/get", "tools/list"])
async def test_missing_token_is_rejected_and_handler_is_not_run(method):
    call_next = Recorder()

    with _patch_token(None):
        with pytest.raises(UnauthenticatedError):
            await Auth0ContextMiddleware(StubMcpClient()).on_request(_context(method), call_next)

    assert call_next.seen is None


@pytest.mark.parametrize("method", ["initialize", "ping", "server/discover"])
async def test_lifecycle_requests_pass_through_without_a_token(method):
    stub = StubMcpClient()
    call_next = Recorder()

    with _patch_token(None):
        result = await Auth0ContextMiddleware(stub).on_request(_context(method), call_next)

    assert result == "result"
    assert call_next.seen == (None, None)
    assert stub.bound == []


async def test_caller_is_visible_inside_a_resource_and_a_prompt():
    async def whoami_resource() -> str:
        return get_caller_principal().sub

    async def whoami_prompt() -> str:
        return get_caller_principal().sub

    server = FastMCP(name="test", middleware=[Auth0ContextMiddleware(StubMcpClient())])
    server.resource("res://whoami")(whoami_resource)
    server.prompt(whoami_prompt)
    with _patch_token(_access_token()):
        async with Client(server) as client:
            resource = await client.read_resource("res://whoami")
            prompt = await client.get_prompt("whoami_prompt")

    assert resource[0].text == "u"
    assert prompt.messages[0].content.text == "u"


async def test_claims_that_build_principal_rejects_never_reach_the_handler():
    call_next = Recorder()

    with _patch_token(_access_token({"azp": "cid", "exp": 9999})):
        with pytest.raises(VerifyAccessTokenError):
            await Auth0ContextMiddleware(StubMcpClient()).on_request(_context(), call_next)

    assert call_next.seen is None


_API_ERROR = ApiError("federated_connection_refresh_token_not_found", "tenant detail XYZ", 401)
_DOWNSCOPED_ERROR = DownscopedTokenError("Exchanged token did not include all requested scopes.")


async def _call_tool_raising(error, mask_error_details=False):
    async def boom() -> str:
        raise error

    server = FastMCP(
        name="test", mask_error_details=mask_error_details, middleware=[Auth0ContextMiddleware(StubMcpClient())]
    )
    server.tool(boom)
    with _patch_token(_access_token()):
        async with Client(server) as client:
            result = await client.call_tool("boom", {}, raise_on_error=False)
    return result.content[0].text


@pytest.mark.parametrize("mask_error_details", [False, True])
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (_API_ERROR, "Token exchange failed (federated_connection_refresh_token_not_found)"),
        (_DOWNSCOPED_ERROR, "Token exchange failed (downscoped_token)"),
    ],
)
async def test_failed_exchange_reaches_the_client_as_its_error_code_only(error, expected, mask_error_details):
    assert await _call_tool_raising(error, mask_error_details) == expected


async def test_tool_error_raised_by_the_tool_keeps_its_message():
    async def link_account() -> str:
        try:
            raise _API_ERROR
        except ApiError as exc:
            raise ToolError("Link your Google account first") from exc

    server = FastMCP(name="test", middleware=[Auth0ContextMiddleware(StubMcpClient())])
    server.tool(link_account)
    with _patch_token(_access_token()):
        async with Client(server) as client:
            result = await client.call_tool("link_account", {}, raise_on_error=False)

    assert result.content[0].text == "Link your Google account first"


async def test_other_tool_errors_are_left_to_fastmcp():
    assert await _call_tool_raising(RuntimeError("internal detail")) == "Error calling tool 'boom': internal detail"


async def _read_resource_raising(error, mask_error_details=False):
    async def boom() -> str:
        raise error

    server = FastMCP(
        name="test", mask_error_details=mask_error_details, middleware=[Auth0ContextMiddleware(StubMcpClient())]
    )
    server.resource("res://boom")(boom)
    with _patch_token(_access_token()):
        async with Client(server) as client:
            with pytest.raises(Exception) as exc_info:
                await client.read_resource("res://boom")
    return str(exc_info.value)


async def _get_prompt_raising(error, mask_error_details=False):
    async def boom() -> str:
        raise error

    server = FastMCP(
        name="test", mask_error_details=mask_error_details, middleware=[Auth0ContextMiddleware(StubMcpClient())]
    )
    server.prompt(boom)
    with _patch_token(_access_token()):
        async with Client(server) as client:
            with pytest.raises(Exception) as exc_info:
                await client.get_prompt("boom")
    return str(exc_info.value)


@pytest.mark.parametrize("mask_error_details", [False, True])
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (_API_ERROR, "Token exchange failed (federated_connection_refresh_token_not_found)"),
        (_DOWNSCOPED_ERROR, "Token exchange failed (downscoped_token)"),
    ],
)
async def test_failed_exchange_in_a_resource_reaches_the_client_as_its_error_code_only(
    error, expected, mask_error_details
):
    assert await _read_resource_raising(error, mask_error_details) == expected


@pytest.mark.parametrize("mask_error_details", [False, True])
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (_API_ERROR, "Token exchange failed (federated_connection_refresh_token_not_found)"),
        (_DOWNSCOPED_ERROR, "Token exchange failed (downscoped_token)"),
    ],
)
async def test_failed_exchange_in_a_prompt_reaches_the_client_as_its_error_code_only(
    error, expected, mask_error_details
):
    assert await _get_prompt_raising(error, mask_error_details) == expected


async def test_resource_error_raised_by_the_resource_keeps_its_message():
    async def link_account() -> str:
        try:
            raise _API_ERROR
        except ApiError as exc:
            raise ResourceError("Link your Google account first") from exc

    server = FastMCP(name="test", middleware=[Auth0ContextMiddleware(StubMcpClient())])
    server.resource("res://link")(link_account)
    with _patch_token(_access_token()):
        async with Client(server) as client:
            with pytest.raises(Exception, match="Link your Google account first"):
                await client.read_resource("res://link")


async def test_prompt_error_raised_by_the_prompt_keeps_its_message():
    async def link_account() -> str:
        try:
            raise _API_ERROR
        except ApiError as exc:
            raise PromptError("Link your Google account first") from exc

    server = FastMCP(name="test", middleware=[Auth0ContextMiddleware(StubMcpClient())])
    server.prompt(link_account)
    with _patch_token(_access_token()):
        async with Client(server) as client:
            with pytest.raises(Exception, match="Link your Google account first"):
                await client.get_prompt("link_account")


async def test_other_resource_and_prompt_errors_are_left_to_fastmcp():
    assert await _read_resource_raising(RuntimeError("internal detail")) == (
        "Error reading resource 'res://boom': internal detail"
    )
    assert await _get_prompt_raising(RuntimeError("internal detail")) == (
        "Error rendering prompt 'boom': internal detail"
    )


async def test_failed_exchange_in_a_mounted_server_is_still_shortened():
    async def boom() -> str:
        raise _API_ERROR

    child = FastMCP(name="child")
    child.tool(boom)
    parent = FastMCP(name="parent", middleware=[Auth0ContextMiddleware(StubMcpClient())])
    parent.mount(child, namespace="child")
    with _patch_token(_access_token()):
        async with Client(parent) as client:
            result = await client.call_tool("child_boom", {}, raise_on_error=False)

    assert result.content[0].text == "Token exchange failed (federated_connection_refresh_token_not_found)"


async def test_failed_exchange_in_a_mounted_resource_and_prompt_is_still_shortened():
    async def boom_resource() -> str:
        raise _API_ERROR

    async def boom_prompt() -> str:
        raise _API_ERROR

    child = FastMCP(name="child")
    child.resource("res://boom")(boom_resource)
    child.prompt(boom_prompt)
    parent = FastMCP(name="parent", middleware=[Auth0ContextMiddleware(StubMcpClient())])
    parent.mount(child, namespace="child")
    expected = "Token exchange failed (federated_connection_refresh_token_not_found)"
    with _patch_token(_access_token()):
        async with Client(parent) as client:
            resources = await client.list_resources()
            with pytest.raises(Exception) as resource_error:
                await client.read_resource(str(resources[0].uri))
            with pytest.raises(Exception) as prompt_error:
                await client.get_prompt("child_boom_prompt")

    assert str(resource_error.value) == expected
    assert str(prompt_error.value) == expected
