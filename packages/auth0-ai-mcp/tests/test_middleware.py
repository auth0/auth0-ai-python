"""ASGI middleware behavior: bearer handling, request context, and protected-resource metadata."""

import base64
import json
import logging
from types import SimpleNamespace

import httpx
import pytest
from auth0_api_python.errors import (
    AuthServerUnavailableError,
    ConfigurationError,
    VerifyAccessTokenError,
)
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.authentication import AuthCredentials

from auth0_ai_mcp import (
    McpServerClient,
    create_mcp_client,
    get_caller_mcp_client,
    get_caller_principal,
)
from auth0_ai_mcp.middleware import (
    Auth0AsgiMiddleware,
    build_protected_resource_metadata,
    build_www_authenticate,
)

RESOURCE_URL = "https://mcp.example/mcp"
DOMAIN = "tenant.example"
PRM_URL = "https://mcp.example/.well-known/oauth-protected-resource/mcp"


class StubApiClient:
    """Stands in for auth0-api-python's ApiClient, returning claims or raising on verify and recording exchanges."""

    def __init__(self, *, claims=None, raises=None, domain=DOMAIN, audience=RESOURCE_URL, domains=None):
        self.claims = claims
        self.raises = raises
        self.options = SimpleNamespace(domain=domain, audience=audience, domains=domains)
        self.verified_tokens = []
        self.exchanged = []

    async def verify_access_token(self, access_token):
        self.verified_tokens.append(access_token)
        if self.raises is not None:
            raise self.raises
        return self.claims

    async def get_token_on_behalf_of(self, access_token, audience, scope, *, verified):
        self.exchanged.append((access_token, verified.claims))
        return {"access_token": "downstream", "expires_at": 4102444800}


class StubApp:
    """Records whether it ran and which caller it saw."""

    def __init__(self, *, raises=None):
        self.raises = raises
        self.calls = 0
        self.seen_principal = None
        self.seen_client = None
        self.seen_scope = None

    async def __call__(self, scope, receive, send):
        self.calls += 1
        self.seen_principal = get_caller_principal()
        self.seen_client = get_caller_mcp_client()
        self.seen_scope = scope
        if self.raises is not None:
            raise self.raises


def _middleware(app, api, **kwargs):
    return Auth0AsgiMiddleware(
        app,
        mcp_client=McpServerClient(api),
        **kwargs,
    )


def _scope(path="/mcp", headers=None, scope_type="http", method="POST"):
    return {"type": scope_type, "path": path, "method": method, "headers": headers or []}


def _bearer(token):
    return [(b"authorization", f"Bearer {token}".encode())]


async def _call(middleware, scope):
    sent = []

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        sent.append(message)

    await middleware(scope, receive, send)
    return sent


def _status(sent):
    return sent[0]["status"]


def _header(sent, name):
    return dict(sent[0]["headers"]).get(name)


def _body(sent):
    return json.loads(sent[1]["body"])


def _claims(**overrides):
    claims = {"sub": "user_1", "exp": 4102444800, "scope": "read:x write:x", "azp": "client_1"}
    claims.update(overrides)
    return claims


async def test_missing_bearer_token_returns_401_and_skips_app():
    app = StubApp()
    api = StubApiClient(claims=_claims())

    sent = await _call(_middleware(app, api), _scope())

    assert _status(sent) == 401
    assert _header(sent, b"www-authenticate") == f'Bearer resource_metadata="{PRM_URL}"'.encode()
    assert _body(sent) == {
        "jsonrpc": "2.0",
        "error": {"code": -32001, "message": "Unauthorized"},
        "id": None,
    }
    assert app.calls == 0
    assert api.verified_tokens == []


async def test_non_bearer_authorization_header_is_treated_as_missing():
    app = StubApp()

    sent = await _call(
        _middleware(app, StubApiClient(claims=_claims())),
        _scope(headers=[(b"authorization", b"Basic abc123")]),
    )

    assert _status(sent) == 401
    assert app.calls == 0


@pytest.mark.parametrize("value", [b"Bearer ", b"Bearer    ", b"bearer \t"])
async def test_blank_bearer_token_is_treated_as_missing(value):
    app = StubApp()
    api = StubApiClient(claims=_claims())

    sent = await _call(_middleware(app, api), _scope(headers=[(b"authorization", value)]))

    assert _status(sent) == 401
    assert _header(sent, b"www-authenticate") == f'Bearer resource_metadata="{PRM_URL}"'.encode()
    assert app.calls == 0
    assert api.verified_tokens == []


async def test_bearer_scheme_is_matched_case_insensitively():
    app = StubApp()
    api = StubApiClient(claims=_claims())

    await _call(_middleware(app, api), _scope(headers=[(b"authorization", b"bearer good")]))

    assert app.calls == 1
    assert api.verified_tokens == ["good"]


async def test_challenge_uses_root_metadata_url_when_resource_has_no_path():
    middleware = Auth0AsgiMiddleware(
        StubApp(),
        mcp_client=McpServerClient(StubApiClient(claims=_claims(), audience="https://mcp.example/")),
    )

    sent = await _call(middleware, _scope())

    assert _header(sent, b"www-authenticate") == (
        b'Bearer resource_metadata="https://mcp.example/.well-known/oauth-protected-resource"'
    )


def _unsigned_jwt(header, payload):
    def encode(value):
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()

    return f"{encode(header)}.{encode(payload)}.signature"


@pytest.mark.parametrize(
    "header, payload, reason",
    [
        ([1], {}, "segment is not a JSON object"),
        ({"alg": 5}, {}, "'alg' must be a string"),
        ({"alg": "RS256", "kid": "k"}, [1], "segment is not a JSON object"),
    ],
)
async def test_a_malformed_token_returns_401_for_a_real_client(header, payload, reason, caplog):
    app = StubApp()
    middleware = Auth0AsgiMiddleware(app, mcp_client=create_mcp_client(DOMAIN, RESOURCE_URL))

    with caplog.at_level(logging.WARNING, logger="auth0_ai_mcp.middleware"):
        sent = await _call(middleware, _scope(headers=_bearer(_unsigned_jwt(header, payload))))

    assert _status(sent) == 401
    assert b'error="invalid_token"' in _header(sent, b"www-authenticate")
    assert reason in caplog.text
    assert app.calls == 0


async def test_invalid_token_gets_a_fixed_description_and_the_reason_is_only_logged(caplog):
    app = StubApp()
    api = StubApiClient(raises=VerifyAccessTokenError('Signature verification failed: detail\r\nInjected: "header"'))

    with caplog.at_level(logging.WARNING, logger="auth0_ai_mcp.middleware"):
        sent = await _call(_middleware(app, api), _scope(headers=_bearer("secret-tok")))

    assert _status(sent) == 401
    assert app.calls == 0
    assert api.verified_tokens == ["secret-tok"]
    assert "Injected" not in _header(sent, b"www-authenticate").decode()
    assert "Injected" not in json.dumps(_body(sent))
    assert _header(sent, b"www-authenticate") == (
        b'Bearer error="invalid_token", error_description="The access token is not valid", '
        + f'resource_metadata="{PRM_URL}"'.encode()
    )
    assert _body(sent)["error"] == {
        "code": -32001,
        "message": "Unauthorized: The access token is not valid",
    }
    assert "Signature verification failed: detail" in caplog.text
    assert "secret-tok" not in caplog.text


async def test_unreachable_auth_server_returns_503_without_a_challenge_and_skips_app(caplog):
    app = StubApp()
    api = StubApiClient(raises=AuthServerUnavailableError("Failed to fetch JWKS"))

    with caplog.at_level(logging.ERROR, logger="auth0_ai_mcp.middleware"):
        sent = await _call(_middleware(app, api), _scope(headers=_bearer("tok")))

    assert _status(sent) == 503
    assert _header(sent, b"retry-after") == b"5"
    assert _header(sent, b"www-authenticate") is None
    assert _body(sent)["error"]["code"] == -32002
    assert "Failed to fetch JWKS" not in json.dumps(_body(sent))
    assert "Failed to fetch JWKS" in caplog.text
    assert app.calls == 0


async def test_non_verification_errors_propagate():
    api = StubApiClient(raises=ValueError("misconfigured"))
    app = StubApp()

    with pytest.raises(ValueError):
        await _call(_middleware(app, api), _scope(headers=_bearer("tok")))

    assert app.calls == 0


async def test_claims_without_sub_return_401_and_skip_app():
    app = StubApp()
    api = StubApiClient(claims=_claims(sub=""))

    sent = await _call(_middleware(app, api), _scope(headers=_bearer("tok")))

    assert _status(sent) == 401
    assert app.calls == 0


def test_build_www_authenticate_with_error():
    assert build_www_authenticate(PRM_URL, "invalid_token", "Expired") == (
        f'Bearer error="invalid_token", error_description="Expired", resource_metadata="{PRM_URL}"'
    )


def test_build_www_authenticate_sanitizes_every_value():
    challenge = build_www_authenticate('https://h/"x\\', 'bad"\r\n', 'say "hi"\\\r\nX: y \u00e9\u2603')

    assert challenge == (
        "Bearer error=\"bad'  \", error_description=\"say 'hi'   X: y   \", "
        "resource_metadata=\"https://h/'x \""
    )
    challenge.encode("ascii")


async def test_valid_token_runs_app_with_caller_in_context():
    app = StubApp()
    api = StubApiClient(claims=_claims())

    sent = await _call(_middleware(app, api), _scope(headers=_bearer("good")))

    assert sent == []
    assert app.calls == 1
    assert app.seen_principal.sub == "user_1"
    assert app.seen_principal.scopes == ["read:x", "write:x"]
    assert api.verified_tokens == ["good"]


async def test_context_client_is_bound_to_the_verified_token():
    app = StubApp()
    api = StubApiClient(claims=_claims())

    await _call(_middleware(app, api), _scope(headers=_bearer("good")))

    await app.seen_client.get_token_on_behalf_of(audience="https://orders/")

    assert app.seen_client.get_principal() is app.seen_principal
    assert api.exchanged == [("good", _claims())]


async def test_valid_token_sets_authenticated_user_without_the_raw_token():
    app = StubApp()
    api = StubApiClient(claims=_claims(iss="https://tenant.example/"))

    await _call(_middleware(app, api), _scope(headers=_bearer("raw-bearer-value")))

    user = app.seen_scope["user"]
    auth = app.seen_scope["auth"]
    assert isinstance(user, AuthenticatedUser)
    assert isinstance(auth, AuthCredentials)
    assert user.access_token.client_id == "client_1"
    assert user.access_token.subject == "user_1"
    assert user.access_token.claims == {"iss": "https://tenant.example/"}
    assert auth.scopes == ["read:x", "write:x"]
    assert user.access_token.token != "raw-bearer-value"
    assert "raw-bearer-value" not in repr(vars(user)) + user.access_token.model_dump_json()
    assert "raw-bearer-value" not in repr(vars(auth))


async def test_rejected_token_sets_no_user_on_the_scope():
    scope = _scope(headers=_bearer("bad"))

    await _call(_middleware(StubApp(), StubApiClient(raises=VerifyAccessTokenError("x"))), scope)

    assert "user" not in scope and "auth" not in scope


_SESSION_CLAIMS = {
    "alice-1": {"sub": "alice", "azp": "c1", "iss": "https://t/", "exp": 4102444800},
    "alice-2": {"sub": "alice", "azp": "c1", "iss": "https://t/", "exp": 4102444900},
    "bob-1": {"sub": "bob", "azp": "c1", "iss": "https://t/", "exp": 4102444800},
}


class StubTokenTableApiClient:
    """Maps each bearer value to its own claim set."""

    options = SimpleNamespace(domain=DOMAIN, audience=RESOURCE_URL, domains=None)

    async def verify_access_token(self, access_token):
        return _SESSION_CLAIMS[access_token]


async def test_mcp_session_stays_bound_to_the_caller_that_opened_it():
    manager = StreamableHTTPSessionManager(app=Server("test"), json_response=True)
    middleware = Auth0AsgiMiddleware(
        manager.handle_request,
        mcp_client=McpServerClient(StubTokenTableApiClient()),
    )
    headers = {"accept": "application/json, text/event-stream", "content-type": "application/json"}
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1"},
        },
    }
    ping = {"jsonrpc": "2.0", "id": 2, "method": "ping"}

    async with manager.run(), httpx.AsyncClient(
        transport=httpx.ASGITransport(app=middleware), base_url="http://localhost"
    ) as http:
        opened = await http.post(
            "/mcp", headers={**headers, "authorization": "Bearer alice-1"}, json=initialize
        )
        session = {"mcp-session-id": opened.headers["mcp-session-id"], "mcp-protocol-version": "2025-06-18"}

        other = await http.post(
            "/mcp", headers={**headers, **session, "authorization": "Bearer bob-1"}, json=ping
        )
        same = await http.post(
            "/mcp", headers={**headers, **session, "authorization": "Bearer alice-2"}, json=ping
        )

    assert opened.status_code == 200
    assert other.status_code == 404
    assert same.status_code == 200


async def test_context_is_reset_after_request():
    await _call(
        _middleware(StubApp(), StubApiClient(claims=_claims())),
        _scope(headers=_bearer("good")),
    )

    assert get_caller_principal() is None


async def test_context_is_reset_when_app_raises():
    app = StubApp(raises=RuntimeError("handler failed"))
    middleware = _middleware(app, StubApiClient(claims=_claims()))

    with pytest.raises(RuntimeError):
        await _call(middleware, _scope(headers=_bearer("good")))

    assert app.calls == 1
    assert get_caller_principal() is None


async def test_lifespan_scope_passes_through_without_verification():
    app = StubApp()
    api = StubApiClient(claims=_claims())

    sent = await _call(_middleware(app, api), {"type": "lifespan"})

    assert sent == []
    assert app.calls == 1
    assert api.verified_tokens == []


async def test_websocket_scope_is_closed_without_running_the_app():
    app = StubApp()
    api = StubApiClient(claims=_claims())

    sent = await _call(_middleware(app, api), _scope(scope_type="websocket", headers=_bearer("good")))

    assert sent == [{"type": "websocket.close", "code": 1008}]
    assert app.calls == 0
    assert api.verified_tokens == []


async def test_options_preflight_passes_through_without_verification_or_context():
    app = StubApp()
    api = StubApiClient(claims=_claims())

    sent = await _call(_middleware(app, api), _scope(method="OPTIONS"))

    assert sent == []
    assert app.calls == 1
    assert app.seen_principal is None
    assert api.verified_tokens == []


async def test_metadata_route_is_served_without_a_token():
    app = StubApp()
    api = StubApiClient(claims=_claims())

    sent = await _call(
        _middleware(app, api, scopes_supported=["read:x"]),
        _scope(path="/.well-known/oauth-protected-resource", method="GET"),
    )

    assert _status(sent) == 200
    assert _body(sent) == {
        "resource": RESOURCE_URL,
        "authorization_servers": [f"https://{DOMAIN}/"],
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["read:x"],
    }
    assert app.calls == 0
    assert api.verified_tokens == []


def test_metadata_omits_scopes_supported_when_not_given():
    doc = build_protected_resource_metadata(McpServerClient(StubApiClient()))

    assert "scopes_supported" not in doc


def test_metadata_omits_resource_name_and_documentation_when_not_given():
    doc = build_protected_resource_metadata(McpServerClient(StubApiClient()))

    assert "resource_name" not in doc
    assert "resource_documentation" not in doc
    assert "jwks_uri" not in doc


async def test_metadata_includes_resource_name_and_documentation_when_given():
    sent = await _call(
        _middleware(
            StubApp(),
            StubApiClient(claims=_claims()),
            resource_name="Orders MCP",
            resource_documentation="https://docs.example/orders",
        ),
        _scope(path="/.well-known/oauth-protected-resource", method="GET"),
    )

    body = _body(sent)
    assert body["resource_name"] == "Orders MCP"
    assert body["resource_documentation"] == "https://docs.example/orders"


async def test_metadata_is_served_at_the_path_suffixed_route():
    app = StubApp()

    sent = await _call(
        _middleware(app, StubApiClient(claims=_claims())),
        _scope(path="/.well-known/oauth-protected-resource/mcp", method="GET"),
    )

    assert _status(sent) == 200
    assert _body(sent)["resource"] == RESOURCE_URL
    assert app.calls == 0


async def test_metadata_route_keeps_a_trailing_slash_in_the_resource_path():
    middleware = Auth0AsgiMiddleware(
        StubApp(),
        mcp_client=McpServerClient(StubApiClient(claims=_claims(), audience="https://mcp.example/mcp/")),
    )

    served = await _call(middleware, _scope(path="/.well-known/oauth-protected-resource/mcp/", method="GET"))
    challenged = await _call(middleware, _scope())

    assert _status(served) == 200
    assert _header(challenged, b"www-authenticate") == (
        b'Bearer resource_metadata="https://mcp.example/.well-known/oauth-protected-resource/mcp/"'
    )


@pytest.mark.parametrize(
    "path", ["/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource/mcp"]
)
async def test_metadata_routes_need_a_token_for_methods_other_than_get(path):
    app = StubApp()
    api = StubApiClient(claims=_claims())

    sent = await _call(_middleware(app, api), _scope(path=path, method="POST"))

    assert _status(sent) == 401
    assert app.calls == 0


BUILDERS = [
    lambda client: build_protected_resource_metadata(client),
    lambda client: Auth0AsgiMiddleware(StubApp(), mcp_client=client),
]


@pytest.mark.parametrize(
    "api_options",
    [{"domain": ""}, {"domain": None}, {"domain": None, "domains": ["a.example", "b.example"]}],
    ids=["empty", "none", "multi_domain"],
)
@pytest.mark.parametrize("build", BUILDERS)
def test_a_client_without_a_single_domain_needs_explicit_authorization_servers(build, api_options):
    with pytest.raises(ConfigurationError, match="authorization_servers is required"):
        build(McpServerClient(StubApiClient(**api_options)))


@pytest.mark.parametrize(
    "domain",
    [
        "   ",
        "tenant.example/path",
        "http://tenant.example",
        "https://tenant.example/",
        "tenant.example/",
        " tenant.example",
        "tenant.example\n",
        "tenant .example",
    ],
)
def test_a_client_domain_that_is_not_a_bare_tenant_host_is_rejected(domain):
    with pytest.raises(ConfigurationError, match="tenant domain|bare host"):
        build_protected_resource_metadata(McpServerClient(StubApiClient(domain=domain)))


def test_a_domain_the_core_client_cannot_discover_from_is_rejected_for_a_real_client():
    client = create_mcp_client("https://tenant.example/", RESOURCE_URL)

    with pytest.raises(ConfigurationError, match="bare host"):
        build_protected_resource_metadata(client)


@pytest.mark.parametrize(
    "audience",
    [
        "",
        "orders-api",
        "/mcp",
        "mcp.example/mcp",
        "ftp://mcp.example/mcp",
        "https:///mcp",
        "https://mcp.example/mcp#x",
        "https://user:pass@mcp.example/mcp",
        "https://mcp.example/m cp",
        "https://mcp.ex\tample/mcp",
        None,
    ],
)
def test_an_audience_that_is_not_an_absolute_http_url_is_rejected(audience):
    with pytest.raises(ConfigurationError, match="resource_url"):
        build_protected_resource_metadata(McpServerClient(StubApiClient(audience=audience)))


def test_the_middleware_rejects_an_invalid_audience_too():
    with pytest.raises(ConfigurationError, match="resource_url"):
        Auth0AsgiMiddleware(StubApp(), mcp_client=McpServerClient(StubApiClient(audience="orders-api")))


@pytest.mark.parametrize("resource_url", ["https://mcp.example/other", "https://mcp.example/mcp/", "http://mcp.example/mcp"])
@pytest.mark.parametrize(
    "build",
    [
        lambda client, url: build_protected_resource_metadata(client, resource_url=url),
        lambda client, url: Auth0AsgiMiddleware(StubApp(), mcp_client=client, resource_url=url),
    ],
)
def test_a_resource_url_that_differs_from_the_audience_is_rejected(build, resource_url):
    with pytest.raises(ConfigurationError, match="equal the client audience"):
        build(McpServerClient(StubApiClient()), resource_url)


def test_an_explicit_resource_url_equal_to_the_audience_is_accepted():
    doc = build_protected_resource_metadata(McpServerClient(StubApiClient()), resource_url=RESOURCE_URL)

    assert doc["resource"] == RESOURCE_URL


@pytest.mark.parametrize(
    "domain, expected",
    [
        ("tenant.example", "https://tenant.example/"),
        ("Tenant.Example", "https://tenant.example/"),
        ("tenant.example:8443", "https://tenant.example:8443/"),
    ],
)
def test_the_default_authorization_server_is_the_normalized_client_domain(domain, expected):
    doc = build_protected_resource_metadata(McpServerClient(StubApiClient(domain=domain)))

    assert doc["authorization_servers"] == [expected]


def test_an_http_resource_with_a_port_is_accepted():
    doc = build_protected_resource_metadata(McpServerClient(StubApiClient(audience="http://localhost:3000/mcp")))

    assert doc["resource"] == "http://localhost:3000/mcp"


@pytest.mark.parametrize("api_options", [{}, {"domain": None, "domains": ["a.example", "b.example"]}], ids=["single", "multi"])
def test_explicit_authorization_servers_are_advertised_as_given(api_options):
    servers = ["https://login.example/", "https://other.example/"]

    doc = build_protected_resource_metadata(McpServerClient(StubApiClient(**api_options)), authorization_servers=servers)

    assert doc["authorization_servers"] == servers


@pytest.mark.parametrize(
    "servers",
    [
        [],
        "https://login.example/",
        ["login.example"],
        ["http://login.example/"],
        ["https:///"],
        ["https://login.example/#x"],
        ["https://login.example/?q=1"],
        ["https://user:pass@login.example/"],
        ["https://login .example/"],
        ["https://login.example/\x00"],
        [None],
    ],
)
def test_authorization_servers_must_be_a_non_empty_list_of_https_urls(servers):
    with pytest.raises(ConfigurationError, match="authorization_servers"):
        build_protected_resource_metadata(McpServerClient(StubApiClient()), authorization_servers=servers)


async def test_the_middleware_advertises_the_authorization_servers_it_is_given():
    middleware = _middleware(StubApp(), StubApiClient(), authorization_servers=["https://login.example/"])

    sent = await _call(middleware, _scope(path="/.well-known/oauth-protected-resource", method="GET"))

    assert _body(sent)["authorization_servers"] == ["https://login.example/"]
