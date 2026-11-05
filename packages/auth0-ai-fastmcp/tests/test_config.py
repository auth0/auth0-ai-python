"""Tests for Auth0FastMCP wiring. Network-touching pieces are mocked so this stays offline."""

import importlib.metadata
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from auth0_ai_mcp import (
    AuthServerUnavailableError,
    ConfigurationError,
    VerifiedToken,
    VerifyAccessTokenError,
    get_caller_mcp_client,
    get_caller_principal,
)
from auth0_api_python.token_utils import PRIVATE_JWK, generate_token, generate_token_with_cnf
from fastmcp import FastMCP
from starlette.testclient import TestClient

from auth0_ai_fastmcp.config import Auth0FastMCP, Auth0FastMCPOptions


def _options(**overrides) -> Auth0FastMCPOptions:
    base = {
        "domain": "tenant.auth0.com",
        "resource_url": "https://api.example.com",
        "tool_scopes": ["tool:a", "tool:b"],
        "client_id": "cid",
        "client_secret": "secret",
        "scope_matching": "non_strict",
        "organization_policy": "required",
        "organization_id": "org_abc",
    }
    base.update(overrides)
    return Auth0FastMCPOptions(**base)


def test_options_thread_through_to_create_mcp_client():
    mcp_client = MagicMock()
    with patch("auth0_ai_fastmcp.config.create_mcp_client", return_value=mcp_client) as mock_create:
        with patch("auth0_ai_fastmcp.config._Auth0Provider"):
            Auth0FastMCP(_options())

    mock_create.assert_called_once()
    args, kwargs = mock_create.call_args
    assert args == ("tenant.auth0.com", "https://api.example.com/mcp")
    assert kwargs["client_id"] == "cid"
    assert kwargs["client_secret"] == "secret"
    assert kwargs["scope_matching"] == "non_strict"
    assert kwargs["organization_policy"] == "required"
    assert kwargs["organization_id"] == "org_abc"


def test_client_info_reports_this_package_and_fastmcp_to_create_mcp_client():
    with patch("auth0_ai_fastmcp.config.create_mcp_client") as mock_create:
        with patch("auth0_ai_fastmcp.config._Auth0Provider"):
            Auth0FastMCP(_options())

    assert mock_create.call_args.kwargs["client_info"] == {
        "name": "auth0-ai-fastmcp",
        "version": importlib.metadata.version("auth0-ai-fastmcp"),
        "env": {"fastmcp": importlib.metadata.version("fastmcp")},
    }


def test_client_info_reaches_the_core_client_with_every_layer_in_env():
    with patch("auth0_ai_fastmcp.config._Auth0Provider"):
        auth = Auth0FastMCP(_options(scope_matching="strict"))

    client_info = auth.mcp_client._api.options.client_info
    assert client_info["name"] == "auth0-ai-fastmcp"
    assert client_info["env"] == {
        "fastmcp": importlib.metadata.version("fastmcp"),
        "auth0-ai-mcp": importlib.metadata.version("auth0-ai-mcp"),
    }


def test_client_info_versions_are_unknown_when_the_packages_are_not_installed(monkeypatch):
    def missing(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", missing)
    with patch("auth0_ai_fastmcp.config.create_mcp_client") as mock_create:
        with patch("auth0_ai_fastmcp.config._Auth0Provider"):
            Auth0FastMCP(_options())

    client_info = mock_create.call_args.kwargs["client_info"]
    assert client_info["version"] == "unknown"
    assert client_info["env"] == {"fastmcp": "unknown"}


def test_scope_matching_and_organization_policy_default_to_strict_and_allow():
    options = Auth0FastMCPOptions(domain="tenant.auth0.com", resource_url="https://api.example.com")

    assert options.scope_matching == "strict"
    assert options.organization_policy == "allow"


def test_repr_does_not_include_the_client_secret():
    assert "s3cret-value" not in repr(_options(client_secret="s3cret-value"))


def test_token_store_reaches_create_mcp_client():
    store = MagicMock()
    with patch("auth0_ai_fastmcp.config.create_mcp_client") as mock_create:
        with patch("auth0_ai_fastmcp.config._Auth0Provider"):
            Auth0FastMCP(_options(token_store=store))

    assert mock_create.call_args.kwargs["token_store"] is store


def test_token_store_is_held_by_the_core_client():
    store = MagicMock()
    with patch("auth0_ai_fastmcp.config._Auth0Provider"):
        auth = Auth0FastMCP(_options(token_store=store, scope_matching="strict"))

    assert auth.mcp_client._api.options.token_store is store


def test_mcp_client_property_returns_the_created_client():
    mcp_client = MagicMock()
    with patch("auth0_ai_fastmcp.config.create_mcp_client", return_value=mcp_client):
        with patch("auth0_ai_fastmcp.config._Auth0Provider"):
            auth0 = Auth0FastMCP(_options())

    assert auth0.mcp_client is mcp_client


async def test_provider_gets_metadata_and_delegating_verifier():
    mcp_client = MagicMock()
    mcp_client.verify_access_token = AsyncMock(side_effect=VerifyAccessTokenError("bad"))
    with patch("auth0_ai_fastmcp.config.create_mcp_client", return_value=mcp_client):
        with patch("auth0_ai_fastmcp.config._Auth0Provider") as mock_provider:
            auth0 = Auth0FastMCP(_options())

    kwargs = mock_provider.call_args.kwargs
    assert kwargs["config_url"] == "https://tenant.auth0.com/.well-known/openid-configuration"
    assert kwargs["base_url"] == "https://api.example.com"
    assert kwargs["resource_base_url"] == "https://api.example.com"
    assert kwargs["scopes_supported"] == ["tool:a", "tool:b"]
    assert await kwargs["token_verifier"].verify_token("tok") is None
    mcp_client.verify_access_token.assert_awaited_once_with("tok")
    assert auth0.provider is mock_provider.return_value


def test_advertised_resource_is_resource_url_plus_mcp_path():
    oidc = MagicMock(
        issuer="https://tenant.auth0.com/", jwks_uri="https://tenant.auth0.com/.well-known/jwks.json"
    )
    with patch(
        "fastmcp.server.auth.providers.auth0.OIDCConfiguration.get_oidc_configuration",
        return_value=oidc,
    ):
        auth0 = Auth0FastMCP(
            _options(
                audience="https://api.example.com/mcp",
                resource_url="https://api.example.com",
                scope_matching="strict",
            )
        )
    app = FastMCP(name="test", auth=auth0.provider).http_app()

    response = TestClient(app).get("/.well-known/oauth-protected-resource/mcp")

    assert response.status_code == 200
    assert response.json()["resource"] == "https://api.example.com/mcp"


def test_audience_follows_a_custom_mcp_path():
    oidc = MagicMock(
        issuer="https://tenant.auth0.com/", jwks_uri="https://tenant.auth0.com/.well-known/jwks.json"
    )
    with patch("auth0_ai_fastmcp.config.create_mcp_client") as mock_create:
        with patch(
            "fastmcp.server.auth.providers.auth0.OIDCConfiguration.get_oidc_configuration",
            return_value=oidc,
        ):
            auth0 = Auth0FastMCP(_options(mcp_path="/rpc", scope_matching="strict"))
    app = FastMCP(name="test", auth=auth0.provider).http_app(path="/rpc")

    response = TestClient(app).get("/.well-known/oauth-protected-resource/rpc")

    assert mock_create.call_args.args[1] == "https://api.example.com/rpc"
    assert response.json()["resource"] == mock_create.call_args.args[1]


def _build_with_real_provider(**overrides):
    oidc = MagicMock(
        issuer="https://tenant.auth0.com/", jwks_uri="https://tenant.auth0.com/.well-known/jwks.json"
    )
    with patch("auth0_ai_fastmcp.config.create_mcp_client") as mock_create:
        with patch(
            "fastmcp.server.auth.providers.auth0.OIDCConfiguration.get_oidc_configuration",
            return_value=oidc,
        ):
            auth0 = Auth0FastMCP(_options(scope_matching="strict", **overrides))
    return auth0, mock_create


@pytest.mark.parametrize("resource_url", ["https://API.Example.com:443", "https://api.example.com/"])
def test_the_audience_matches_the_url_fastmcp_advertises_after_normalizing_it(resource_url):
    auth0, mock_create = _build_with_real_provider(resource_url=resource_url)
    app = FastMCP(name="test", auth=auth0.provider).http_app()

    response = TestClient(app).get("/.well-known/oauth-protected-resource/mcp")

    assert mock_create.call_args.args[1] == "https://api.example.com/mcp"
    assert response.json()["resource"] == mock_create.call_args.args[1]


@pytest.mark.parametrize(
    "overrides, path",
    [({}, "/rpc"), ({"mcp_path": "/rpc"}, "/mcp")],
)
def test_serving_fastmcp_at_a_path_other_than_mcp_path_fails_at_startup(overrides, path):
    auth0, _ = _build_with_real_provider(**overrides)

    with pytest.raises(ConfigurationError, match="Set mcp_path"):
        FastMCP(name="test", auth=auth0.provider).http_app(path=path)


def test_mounting_at_the_root_advertises_and_binds_the_bare_origin():
    auth0, mock_create = _build_with_real_provider(mcp_path="/")
    app = FastMCP(name="test", auth=auth0.provider).http_app(path="/")

    response = TestClient(app).get("/.well-known/oauth-protected-resource")

    assert mock_create.call_args.args[1] == "https://api.example.com/"
    assert response.json()["resource"] == mock_create.call_args.args[1]


def test_a_root_mounted_provider_accepts_no_path():
    auth0, _ = _build_with_real_provider(mcp_path="/")

    auth0.provider.get_routes(mcp_path=None)


def test_a_provider_built_for_a_path_rejects_no_path():
    auth0, _ = _build_with_real_provider()

    with pytest.raises(ConfigurationError, match="Set mcp_path"):
        auth0.provider.get_routes(mcp_path=None)


def test_an_explicit_audience_equal_to_the_advertised_resource_is_accepted():
    with patch("auth0_ai_fastmcp.config.create_mcp_client") as mock_create:
        with patch("auth0_ai_fastmcp.config._Auth0Provider"):
            Auth0FastMCP(_options(audience="https://api.example.com/mcp"))

    assert mock_create.call_args.args[1] == "https://api.example.com/mcp"


@pytest.mark.parametrize(
    "overrides",
    [
        {"audience": "https://api.example.com/"},
        {"audience": "https://other.example.com/mcp"},
        {"audience": "https://api.example.com/MCP"},
        {"audience": "https://api.example.com/mcp", "mcp_path": "/rpc"},
        {"resource_url": "https://api.example.com/mcp", "audience": "https://api.example.com/mcp"},
    ],
)
def test_an_audience_that_differs_from_the_advertised_resource_is_rejected(overrides):
    with patch("auth0_ai_fastmcp.config.create_mcp_client") as mock_create:
        with patch("auth0_ai_fastmcp.config._Auth0Provider"):
            with pytest.raises(ConfigurationError, match="audience must equal"):
                Auth0FastMCP(_options(**overrides))

    mock_create.assert_not_called()


@pytest.mark.parametrize("resource_url", ["", "api.example.com", "ftp://api.example.com", "https://", "https://api.example.com/#frag", "https://api.example.com?x=1", "https://api.example.com/?x=1", "https://u:p@api.example.com"])
def test_a_resource_url_that_is_not_an_absolute_http_url_is_rejected(resource_url):
    with patch("auth0_ai_fastmcp.config.create_mcp_client") as mock_create:
        with patch("auth0_ai_fastmcp.config._Auth0Provider"):
            with pytest.raises(ConfigurationError, match="resource_url"):
                Auth0FastMCP(_options(resource_url=resource_url))

    mock_create.assert_not_called()


@pytest.mark.parametrize("mcp_path", ["", "mcp", "/mcp?x=1", "/mcp#frag"])
def test_an_mcp_path_without_a_leading_slash_is_rejected(mcp_path):
    with patch("auth0_ai_fastmcp.config.create_mcp_client") as mock_create:
        with patch("auth0_ai_fastmcp.config._Auth0Provider"):
            with pytest.raises(ConfigurationError, match="mcp_path"):
                Auth0FastMCP(_options(mcp_path=mcp_path))

    mock_create.assert_not_called()


def test_required_scopes_are_advertised_alongside_tool_scopes():
    options = _options(tool_scopes=["tool:a", "tool:b"], required_scopes=["tool:b", "read:c"])
    with patch("auth0_ai_fastmcp.config.create_mcp_client"):
        with patch("auth0_ai_fastmcp.config._Auth0Provider") as mock_provider:
            Auth0FastMCP(options)

    assert mock_provider.call_args.kwargs["scopes_supported"] == ["tool:a", "tool:b", "read:c"]
    assert options.tool_scopes == ["tool:a", "tool:b"]


def test_advertised_scopes_reach_the_protected_resource_metadata():
    auth0, _ = _build_with_real_provider(tool_scopes=["tool:a", "tool:b"], required_scopes=["tool:b", "read:c"])
    app = FastMCP(name="test", auth=auth0.provider).http_app()

    response = TestClient(app).get("/.well-known/oauth-protected-resource/mcp")

    assert response.json()["scopes_supported"] == ["tool:a", "tool:b", "read:c"]


@pytest.mark.parametrize(
    "domain",
    ["", "https://tenant.auth0.com", "tenant.auth0.com/", "tenant.auth0.com/path", "tenant .auth0.com", " tenant.auth0.com", "tenant.auth0.com?x", "tenant.auth0.com#", "user@tenant.auth0.com"],
)
def test_a_domain_that_is_not_a_bare_host_is_rejected(domain):
    with patch("auth0_ai_fastmcp.config.create_mcp_client") as mock_create:
        with patch("auth0_ai_fastmcp.config._Auth0Provider") as mock_provider:
            with pytest.raises(ConfigurationError, match="domain"):
                Auth0FastMCP(_options(domain=domain))

    mock_create.assert_not_called()
    mock_provider.assert_not_called()


@pytest.mark.parametrize("field", ["tool_scopes", "required_scopes"])
@pytest.mark.parametrize("scopes", ["read:a", "read:a write:a", ("read:a",), [""], ["read:a write:a"], [" read:a"], ["read:a", 5]])
def test_a_scope_list_that_is_not_a_list_of_plain_scopes_is_rejected(field, scopes):
    with patch("auth0_ai_fastmcp.config.create_mcp_client") as mock_create:
        with patch("auth0_ai_fastmcp.config._Auth0Provider"):
            with pytest.raises(ConfigurationError, match=field):
                Auth0FastMCP(_options(**{field: scopes}))

    mock_create.assert_not_called()


def test_tool_scopes_of_none_is_rejected():
    with patch("auth0_ai_fastmcp.config.create_mcp_client"):
        with patch("auth0_ai_fastmcp.config._Auth0Provider"):
            with pytest.raises(ConfigurationError, match="tool_scopes"):
                Auth0FastMCP(_options(tool_scopes=None))


def test_the_401_challenge_asks_the_client_for_the_tool_scopes():
    auth0, _ = _build_with_real_provider(tool_scopes=["tool:a", "tool:b"], required_scopes=["read:c"])
    app = FastMCP(name="test", auth=auth0.provider).http_app()

    response = TestClient(app).post("/mcp", json=_INITIALIZE)

    assert response.status_code == 401
    assert 'scope="tool:a tool:b read:c"' in response.headers["www-authenticate"]


def test_challenge_scopes_for_an_explicit_scope_list_are_that_list():
    auth0, _ = _build_with_real_provider(tool_scopes=["tool:a"], required_scopes=["read:c"])

    assert auth0.provider.get_challenge_scopes(["only:this"]) == ["only:this"]


def test_required_scopes_reach_the_provider():
    oidc = MagicMock(
        issuer="https://tenant.auth0.com/", jwks_uri="https://tenant.auth0.com/.well-known/jwks.json"
    )
    with patch(
        "fastmcp.server.auth.providers.auth0.OIDCConfiguration.get_oidc_configuration",
        return_value=oidc,
    ):
        auth0 = Auth0FastMCP(_options(required_scopes=["read:a"], scope_matching="strict"))

    assert auth0.provider.required_scopes == ["read:a"]


class StubVerifyingClient:
    """Verifies any token to the claims registered for it."""

    def __init__(self, claims_by_token):
        self._claims_by_token = claims_by_token

    async def verify_access_token(self, access_token):
        return VerifiedToken(access_token=access_token, claims=self._claims_by_token[access_token])

    def with_token(self, verified, principal):
        return self.request_client

    request_client = object()


_INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "test", "version": "0"}},
}


class StubUnreachableClient:
    """Cannot reach Auth0 to verify any token."""

    async def verify_access_token(self, access_token):
        raise AuthServerUnavailableError("Failed to fetch JWKS")


def _build_app(mcp_client, required_scopes=None, tools=()):
    oidc = MagicMock(
        issuer="https://tenant.auth0.com/", jwks_uri="https://tenant.auth0.com/.well-known/jwks.json"
    )
    with patch("auth0_ai_fastmcp.config.create_mcp_client", return_value=mcp_client):
        with patch(
            "fastmcp.server.auth.providers.auth0.OIDCConfiguration.get_oidc_configuration",
            return_value=oidc,
        ):
            auth0 = Auth0FastMCP(_options(required_scopes=required_scopes or [], scope_matching="strict"))
    server = FastMCP(name="test", auth=auth0.provider, middleware=[auth0.middleware])
    for tool in tools:
        server.tool(tool)
    return server.http_app(stateless_http=True)


def _post_initialize(mcp_client, required_scopes=None):
    headers = {"Authorization": "Bearer tok", "Accept": "application/json, text/event-stream"}
    with TestClient(_build_app(mcp_client, required_scopes), raise_server_exceptions=False) as client:
        return client.post("/mcp", headers=headers, json=_INITIALIZE)


def _call_mcp_with(scope, required_scopes):
    claims = {"sub": "u", "azp": "app", "exp": 4102444800, "scope": scope}
    return _post_initialize(StubVerifyingClient({"tok": claims}), required_scopes)


def test_request_missing_a_required_scope_gets_403():
    response = _call_mcp_with("other:scope", ["read:a"])

    assert response.status_code == 403
    assert "insufficient_scope" in response.headers["www-authenticate"]
    assert "Required scope: read:a" in response.headers["www-authenticate"] + response.text


@pytest.mark.parametrize("claim", ["permissions", "scp"])
def test_request_with_the_required_scope_only_in_another_claim_gets_403(claim):
    claims = {"sub": "u", "azp": "app", "exp": 4102444800, "scope": "other:scope", claim: ["read:a"]}

    response = _post_initialize(StubVerifyingClient({"tok": claims}), ["read:a"])

    assert response.status_code == 403


def test_request_with_the_required_scope_reaches_the_server():
    response = _call_mcp_with("read:a", ["read:a"])

    assert response.status_code == 200


def test_request_with_a_token_that_has_no_subject_gets_401():
    claims = {"azp": "app", "exp": 4102444800, "scope": "read:a"}

    response = _post_initialize(StubVerifyingClient({"tok": claims}))

    assert response.status_code == 401


def test_request_gets_503_not_401_when_auth0_cannot_be_reached():
    response = _post_initialize(StubUnreachableClient())

    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
    assert response.headers["cache-control"] == "no-store"
    assert "www-authenticate" not in response.headers
    assert response.json()["error"]["code"] == -32003


def test_outage_on_a_non_mcp_path_also_gets_503():
    headers = {"Authorization": "Bearer tok"}
    with TestClient(_build_app(StubUnreachableClient()), raise_server_exceptions=False) as client:
        response = client.get("/mcp", headers=headers)

    assert response.status_code == 503


def test_outage_never_reaches_a_tool():
    calls = []

    def probe() -> str:
        """Record that the tool ran."""
        calls.append(1)
        return "ran"

    headers = {"Authorization": "Bearer tok", "Accept": "application/json, text/event-stream"}
    call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "probe", "arguments": {}}}
    with TestClient(_build_app(StubUnreachableClient(), tools=[probe]), raise_server_exceptions=False) as client:
        response = client.post("/mcp", headers=headers, json=call)

    assert response.status_code == 503
    assert calls == []


def test_request_without_a_token_still_gets_401_during_an_outage():
    headers = {"Accept": "application/json, text/event-stream"}
    with TestClient(_build_app(StubUnreachableClient()), raise_server_exceptions=False) as client:
        response = client.post("/mcp", headers=headers, json=_INITIALIZE)

    assert response.status_code == 401
    assert "www-authenticate" in response.headers


def test_a_tool_sees_the_caller_verified_from_the_bearer_token():
    def whoami() -> str:
        """Return the caller's subject."""
        return get_caller_principal().sub

    claims = {"sub": "alice", "azp": "app", "exp": 4102444800, "scope": ""}
    app = _build_app(StubVerifyingClient({"tok": claims}), tools=[whoami])
    headers = {"Authorization": "Bearer tok", "Accept": "application/json, text/event-stream"}
    call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "whoami", "arguments": {}}}

    with TestClient(app) as client:
        response = client.post("/mcp", headers=headers, json=call)

    assert response.status_code == 200
    assert "alice" in response.text


def test_middleware_builds_the_caller_client_from_the_same_core_client():
    def same_client() -> str:
        """Report whether the tool got the client the core client built."""
        return str(get_caller_mcp_client() is StubVerifyingClient.request_client)

    claims = {"sub": "alice", "azp": "app", "exp": 4102444800, "scope": ""}
    app = _build_app(StubVerifyingClient({"tok": claims}), tools=[same_client])
    headers = {"Authorization": "Bearer tok", "Accept": "application/json, text/event-stream"}
    call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "same_client", "arguments": {}}}

    with TestClient(app) as client:
        response = client.post("/mcp", headers=headers, json=call)

    assert "True" in response.text


def test_a_tool_sees_the_caller_in_a_stateful_session():
    def whoami() -> str:
        """Return the caller's subject."""
        return get_caller_principal().sub

    claims = {"sub": "alice", "azp": "app", "exp": 4102444800, "scope": ""}
    oidc = MagicMock(
        issuer="https://tenant.auth0.com/", jwks_uri="https://tenant.auth0.com/.well-known/jwks.json"
    )
    with patch("auth0_ai_fastmcp.config.create_mcp_client", return_value=StubVerifyingClient({"tok": claims})):
        with patch(
            "fastmcp.server.auth.providers.auth0.OIDCConfiguration.get_oidc_configuration",
            return_value=oidc,
        ):
            auth0 = Auth0FastMCP(_options(scope_matching="strict"))
    server = FastMCP(name="test", auth=auth0.provider, middleware=[auth0.middleware])
    server.tool(whoami)
    headers = {"Authorization": "Bearer tok", "Accept": "application/json, text/event-stream"}
    initialized = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "whoami", "arguments": {}}}

    with TestClient(server.http_app()) as client:
        session = client.post("/mcp", headers=headers, json=_INITIALIZE).headers["mcp-session-id"]
        headers = {**headers, "mcp-session-id": session}
        client.post("/mcp", headers=headers, json=initialized)
        response = client.post("/mcp", headers=headers, json=call)

    assert response.status_code == 200
    assert "alice" in response.text


def test_a_session_opened_by_one_caller_is_not_usable_by_another():
    def whoami() -> str:
        """Return the caller's subject."""
        return get_caller_principal().sub

    claims = {
        "alice-tok": {"sub": "alice", "azp": "app", "exp": 4102444800, "scope": ""},
        "bob-tok": {"sub": "bob", "azp": "app", "exp": 4102444800, "scope": ""},
    }
    oidc = MagicMock(
        issuer="https://tenant.auth0.com/", jwks_uri="https://tenant.auth0.com/.well-known/jwks.json"
    )
    with patch("auth0_ai_fastmcp.config.create_mcp_client", return_value=StubVerifyingClient(claims)):
        with patch(
            "fastmcp.server.auth.providers.auth0.OIDCConfiguration.get_oidc_configuration",
            return_value=oidc,
        ):
            auth0 = Auth0FastMCP(_options(scope_matching="strict"))
    server = FastMCP(name="test", auth=auth0.provider, middleware=[auth0.middleware])
    server.tool(whoami)
    accept = {"Accept": "application/json, text/event-stream"}
    call = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "whoami", "arguments": {}}}

    with TestClient(server.http_app()) as client:
        session = client.post(
            "/mcp", headers={**accept, "Authorization": "Bearer alice-tok"}, json=_INITIALIZE
        ).headers["mcp-session-id"]
        own = client.post(
            "/mcp", headers={**accept, "Authorization": "Bearer alice-tok", "mcp-session-id": session}, json=call
        )
        response = client.post(
            "/mcp", headers={**accept, "Authorization": "Bearer bob-tok", "mcp-session-id": session}, json=call
        )

    assert own.status_code == 200
    assert response.status_code == 404


def test_the_legacy_sse_message_route_requires_a_token():
    claims = {"tok": {"sub": "alice", "azp": "app", "exp": 4102444800, "scope": ""}}
    oidc = MagicMock(
        issuer="https://tenant.auth0.com/", jwks_uri="https://tenant.auth0.com/.well-known/jwks.json"
    )
    with patch("auth0_ai_fastmcp.config.create_mcp_client", return_value=StubVerifyingClient(claims)):
        with patch(
            "fastmcp.server.auth.providers.auth0.OIDCConfiguration.get_oidc_configuration",
            return_value=oidc,
        ):
            auth0 = Auth0FastMCP(_options(scope_matching="strict", mcp_path="/sse"))
    server = FastMCP(name="test", auth=auth0.provider, middleware=[auth0.middleware])
    ping = {"jsonrpc": "2.0", "id": 1, "method": "ping"}

    with TestClient(server.http_app(transport="sse"), raise_server_exceptions=False) as client:
        response = client.post("/messages/?session_id=abc", json=ping)

    assert response.status_code == 401


_PUBLIC_JWK = {key: PRIVATE_JWK[key] for key in ("kty", "alg", "use", "kid", "n", "e")}
_AUDIENCE = "https://api.example.com/mcp"


@contextmanager
def _real_core_client(jwks_error=None):
    """Runs the real McpServerClient, with only the two HTTP fetches to the tenant replaced."""
    metadata = {"issuer": "https://tenant.auth0.com/", "jwks_uri": "https://tenant.auth0.com/.well-known/jwks.json"}
    jwks = AsyncMock(side_effect=jwks_error) if jwks_error else AsyncMock(return_value=({"keys": [_PUBLIC_JWK]}, None))
    with patch("auth0_api_python.api_client.fetch_oidc_metadata", AsyncMock(return_value=(metadata, None))):
        with patch("auth0_api_python.api_client.fetch_jwks", jwks):
            yield


def _initialize_with_real_core_client(token, **options):
    oidc = MagicMock(issuer="https://tenant.auth0.com/", jwks_uri="https://tenant.auth0.com/.well-known/jwks.json")
    with patch("fastmcp.server.auth.providers.auth0.OIDCConfiguration.get_oidc_configuration", return_value=oidc):
        auth0 = Auth0FastMCP(_options(scope_matching="strict", organization_policy="allow", organization_id=None, **options))
    server = FastMCP(name="test", auth=auth0.provider, middleware=[auth0.middleware])
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json, text/event-stream"}
    with TestClient(server.http_app(stateless_http=True), raise_server_exceptions=False) as client:
        return client.post("/mcp", headers=headers, json=_INITIALIZE)


async def test_a_real_signed_token_for_this_audience_is_accepted():
    token = await generate_token("tenant.auth0.com", "alice", _AUDIENCE, claims={"azp": "app", "scope": "tool:a"})

    with _real_core_client():
        response = _initialize_with_real_core_client(token)

    assert response.status_code == 200


async def test_a_real_signed_token_for_another_audience_gets_401():
    token = await generate_token("tenant.auth0.com", "alice", "https://other.example.com/mcp", claims={"azp": "app"})

    with _real_core_client():
        response = _initialize_with_real_core_client(token)

    assert response.status_code == 401


async def test_a_real_signed_token_bound_to_a_proof_key_gets_401():
    token = await generate_token_with_cnf("tenant.auth0.com", "alice", _AUDIENCE, claims={"azp": "app"})

    with _real_core_client():
        response = _initialize_with_real_core_client(token)

    assert response.status_code == 401


async def test_a_real_client_that_cannot_fetch_the_signing_keys_gets_503():
    token = await generate_token("tenant.auth0.com", "alice", _AUDIENCE, claims={"azp": "app"})

    with _real_core_client(jwks_error=httpx.ConnectError("unreachable")):
        response = _initialize_with_real_core_client(token)

    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
