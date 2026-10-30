"""OBO exchange and downscope-detection behavior."""

import base64
import importlib.metadata
import json
import time

import pytest
from auth0_api_python import ApiClient, ApiClientOptions, VerifiedToken
from auth0_api_python.errors import ApiError, ConfigurationError, GetTokenByExchangeProfileError

from auth0_ai_mcp import (
    AbstractTokenStore,
    DownscopedTokenError,
    GetAccessTokenForConnectionError,
    GetClientCredentialsTokenError,
    IndexedTokenStore,
    McpServerClient,
    Principal,
    RequestScopedMcpClient,
    create_mcp_client,
)


def _jwt(claims: dict) -> str:
    """Build an unsigned JWT carrying the given claims."""
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"header.{payload}.sig"


def _verified(sub: str = "user_1", org_id: str | None = None) -> VerifiedToken:
    """A verified token and its claims for OBO calls."""
    claims = {"sub": sub, "iss": "https://tenant.example/"}
    if org_id is not None:
        claims["org_id"] = org_id
    return VerifiedToken(access_token=_jwt(claims), claims=claims)


_KEEP = object()
_MISSING = object()


class StubApiClient:
    """Stands in for auth0-api-python's ApiClient, recording exchange calls."""

    def __init__(
        self,
        *,
        granted_scope=None,
        include_scope=True,
        expires_at=None,
        raises=None,
        cc_scope_response=None,
        expires_at_override=_KEEP,
    ):
        self.granted_scope = granted_scope
        self.include_scope = include_scope
        self.expires_at = expires_at if expires_at is not None else int(time.time()) + 3600
        self.expires_at_override = expires_at_override
        self.raises = raises
        self.exchange_calls = 0
        self.last_verified = None
        self.last_access_token = None
        self.last_scope = None
        self.cc_calls = 0
        self.cc_last_audience = None
        self.cc_last_scope = None
        self.cc_scope_response = cc_scope_response
        self.connection_calls = 0
        self.last_connection_options = None

    async def verify_access_token(self, access_token: str):
        return {"sub": "user_1", "exp": int(time.time()) + 3600, "scope": "mcp:use"}

    async def get_token_on_behalf_of(self, access_token, audience, scope=None, *, verified=None):
        self.exchange_calls += 1
        self.last_verified = verified
        self.last_access_token = access_token
        self.last_scope = scope
        if self.raises is not None:
            raise self.raises
        granted = self.granted_scope if self.granted_scope is not None else (scope or "")
        result = {
            "access_token": f"downstream-for-{audience}",
            "expires_in": self.expires_at - int(time.time()),
            "expires_at": self.expires_at,
        }
        if self.include_scope:
            result["scope"] = granted
        return self._with_expiry(result)

    def _with_expiry(self, result):
        if self.expires_at_override is _MISSING:
            result.pop("expires_at")
        elif self.expires_at_override is not _KEEP:
            result["expires_at"] = self.expires_at_override
        return result

    async def get_client_credentials_token(self, audience, scope=None):
        self.cc_calls += 1
        self.cc_last_audience = audience
        self.cc_last_scope = scope
        if self.raises is not None:
            raise self.raises
        result = {"access_token": f"m2m-for-{audience}", "expires_in": 3600, "expires_at": self.expires_at}
        if self.cc_scope_response is not None:
            result["scope"] = self.cc_scope_response
        return self._with_expiry(result)

    async def get_access_token_for_connection(self, options, *, verified=None):
        self.connection_calls += 1
        self.last_connection_options = options
        self.last_verified = verified
        if self.raises is not None:
            raise self.raises
        connection = options.get("connection", "")
        return self._with_expiry(
            {"access_token": f"vault-for-{connection}", "expires_in": 3600, "expires_at": self.expires_at}
        )


async def test_exchange_returns_downstream_token():
    api = StubApiClient()
    client = McpServerClient(api)

    result = await client.get_token_on_behalf_of(
        _verified(), audience="https://orders/", scope="cancel:orders"
    )

    assert result == {
        "access_token": "downstream-for-https://orders/",
        "expires_at": api.expires_at,
        "granted_scopes": "cancel:orders",
    }
    assert api.exchange_calls == 1


_ERROR_BY_FLOW = {
    "obo": GetTokenByExchangeProfileError,
    "client_credentials": GetClientCredentialsTokenError,
    "token_vault": GetAccessTokenForConnectionError,
}


async def _run_flow(client: McpServerClient, flow: str, scope: str | None = "cancel:orders"):
    if flow == "obo":
        return await client.get_token_on_behalf_of(_verified(), audience="https://orders/", scope=scope)
    if flow == "client_credentials":
        return await client.get_client_credentials_token(audience="https://orders/", scope=scope)
    return await client.get_token_for_connection(_verified(), connection="google-oauth2")


@pytest.mark.parametrize("flow", ["obo", "client_credentials"])
async def test_absent_scope_in_response_means_granted_matched_and_is_not_downscoped(flow):
    """RFC 6749: an omitted scope field means the grant matched the request."""
    client = McpServerClient(StubApiClient(include_scope=False))

    result = await _run_flow(client, flow, scope="read:orders write:orders")

    assert "granted_scopes" not in result


async def test_verify_access_token_returns_verified_token_carrying_the_original_access_token():
    client = McpServerClient(StubApiClient())

    verified = await client.verify_access_token("the.raw.token")

    assert verified.access_token == "the.raw.token"
    assert verified.claims["sub"] == "user_1"


async def test_exchange_forwards_verified_token_to_core():
    """The verified token is forwarded so core exchanges its access token and skips re-verifying."""
    api = StubApiClient()
    client = McpServerClient(api)
    verified = _verified()

    await client.get_token_on_behalf_of(
        verified, audience="https://orders/", scope="cancel:orders"
    )

    assert api.last_verified is verified
    assert api.last_verified.claims["sub"] == "user_1"


async def test_downscoped_exchange_raises_downscoped_token_error():
    """A shortfall between requested and granted scopes raises the MCP-owned error."""
    api = StubApiClient(granted_scope="read:orders")
    client = McpServerClient(api)

    with pytest.raises(DownscopedTokenError):
        await client.get_token_on_behalf_of(
            _verified(), audience="https://orders/", scope="cancel:orders"
        )


def test_downscoped_error_has_distinct_error_code():
    error = DownscopedTokenError("x")
    assert error.get_error_code() == "downscoped_token"
    assert error.get_status_code() == 403


async def test_downscoped_error_message_does_not_leak_scopes():
    """The message stays generic and never embeds the granted or missing scope values."""
    api = StubApiClient(granted_scope="read:orders")
    client = McpServerClient(api)

    with pytest.raises(DownscopedTokenError) as exc_info:
        await client.get_token_on_behalf_of(
            _verified(), audience="https://orders/", scope="cancel:orders"
        )

    message = str(exc_info.value)
    assert "cancel:orders" not in message
    assert "read:orders" not in message


@pytest.mark.parametrize("flow", ["obo", "client_credentials"])
async def test_empty_scope_in_response_is_downscoped(flow):
    """A present but empty scope field means nothing was granted, unlike an absent one."""
    client = McpServerClient(StubApiClient(granted_scope="", cc_scope_response=""))

    with pytest.raises(DownscopedTokenError):
        await _run_flow(client, flow)


async def test_no_requested_scope_skips_downscope_check():
    api = StubApiClient(granted_scope="read:orders")
    client = McpServerClient(api)

    result = await client.get_token_on_behalf_of(
        _verified(), audience="https://orders/", scope=None
    )

    assert result["access_token"] == "downstream-for-https://orders/"


async def test_exchange_rejection_propagates_core_error():
    """A core ApiError from the exchange propagates unchanged. The MCP layer does not wrap it."""
    api = StubApiClient(raises=ApiError("access_denied", "rejected by Auth0", 403))
    client = McpServerClient(api)

    with pytest.raises(ApiError):
        await client.get_token_on_behalf_of(
            _verified(), audience="https://orders/", scope="read:orders"
        )


@pytest.mark.parametrize("flow", ["obo", "client_credentials", "token_vault"])
@pytest.mark.parametrize(
    "expires_at",
    [int(time.time()) - 1, _MISSING, None, "soon"],
    ids=["past", "missing", "none", "non_numeric"],
)
async def test_result_without_a_future_numeric_expires_at_is_rejected(flow, expires_at):
    client = McpServerClient(StubApiClient(expires_at_override=expires_at))

    with pytest.raises(_ERROR_BY_FLOW[flow]):
        await _run_flow(client, flow)


async def test_get_client_credentials_token_returns_token_set():
    api = StubApiClient()
    client = McpServerClient(api)

    result = await client.get_client_credentials_token(audience="https://payments/", scope="process:payments")

    assert result["access_token"] == "m2m-for-https://payments/"
    assert api.cc_calls == 1
    assert api.cc_last_audience == "https://payments/"
    assert api.cc_last_scope == "process:payments"


async def test_get_client_credentials_token_raises_when_downscoped():
    api = StubApiClient(cc_scope_response="read:payments")
    client = McpServerClient(api)

    with pytest.raises(DownscopedTokenError):
        await client.get_client_credentials_token(
            audience="https://payments/", scope="process:payments read:payments"
        )


async def test_get_client_credentials_token_passes_when_granted_is_a_reordered_superset():
    api = StubApiClient(cc_scope_response="read:payments process:payments extra:scope")
    client = McpServerClient(api)

    result = await client.get_client_credentials_token(
        audience="https://payments/", scope="process:payments read:payments"
    )

    assert result["granted_scopes"] == "read:payments process:payments extra:scope"


async def test_get_client_credentials_token_propagates_error():
    api = StubApiClient(raises=GetClientCredentialsTokenError("no credentials"))
    client = McpServerClient(api)

    with pytest.raises(GetClientCredentialsTokenError):
        await client.get_client_credentials_token(audience="https://payments/")


async def test_get_token_for_connection_returns_token_set():
    api = StubApiClient()
    client = McpServerClient(api)
    verified = _verified()

    result = await client.get_token_for_connection(verified, connection="google-oauth2")

    assert result["access_token"] == "vault-for-google-oauth2"
    assert api.connection_calls == 1
    assert api.last_connection_options == {"connection": "google-oauth2", "access_token": verified.access_token}
    assert api.last_verified is verified


async def test_get_token_for_connection_includes_login_hint_when_provided():
    api = StubApiClient()
    client = McpServerClient(api)
    verified = _verified()

    await client.get_token_for_connection(verified, connection="google-oauth2", login_hint="user@example.com")

    assert api.last_connection_options == {
        "connection": "google-oauth2",
        "access_token": verified.access_token,
        "login_hint": "user@example.com",
    }


async def test_get_token_for_connection_skips_downscope_check():
    """Token Vault scopes are set on the connection, so a granted scope field is not compared."""
    api = StubApiClient()

    async def connection_with_scope(options, *, verified=None):
        return {"access_token": "vault", "expires_in": 3600, "expires_at": api.expires_at, "scope": "other"}

    api.get_access_token_for_connection = connection_with_scope
    client = McpServerClient(api)

    result = await client.get_token_for_connection(_verified(), connection="google-oauth2")

    assert result["access_token"] == "vault"
    assert result["granted_scopes"] == "other"


async def test_get_token_for_connection_propagates_error():
    api = StubApiClient(raises=GetAccessTokenForConnectionError("exchange failed"))
    client = McpServerClient(api)

    with pytest.raises(GetAccessTokenForConnectionError):
        await client.get_token_for_connection(_verified(), connection="google-oauth2")


def _principal() -> Principal:
    return Principal(sub="user_1", expires_at=9999999999, scopes=[], permissions=None, client_id="client_1", org_id=None)


async def test_request_scoped_get_token_on_behalf_of_forwards_scope_and_verified_token():
    api = StubApiClient()
    verified = _verified()
    scoped = RequestScopedMcpClient(McpServerClient(api), verified, _principal())

    await scoped.get_token_on_behalf_of(audience="https://orders/", scope="cancel:orders")

    assert api.last_scope == "cancel:orders"
    assert api.last_access_token == verified.access_token
    assert api.last_verified is verified


async def test_request_scoped_get_client_credentials_token():
    api = StubApiClient()
    server_client = McpServerClient(api)
    scoped = RequestScopedMcpClient(server_client, _verified(), _principal())

    result = await scoped.get_client_credentials_token(audience="https://payments/", scope="process:payments")

    assert result["access_token"] == "m2m-for-https://payments/"
    assert api.cc_last_audience == "https://payments/"
    assert api.cc_last_scope == "process:payments"


async def test_request_scoped_get_token_for_connection_injects_verified():
    """The request-scoped client injects self._verified. The caller does not supply it."""
    api = StubApiClient()
    verified = _verified()
    server_client = McpServerClient(api)
    scoped = RequestScopedMcpClient(server_client, verified, _principal())

    result = await scoped.get_token_for_connection(connection="google-oauth2", login_hint="user@example.com")

    assert result["access_token"] == "vault-for-google-oauth2"
    assert api.last_verified is verified
    assert api.last_connection_options["login_hint"] == "user@example.com"


@pytest.mark.parametrize(
    "option",
    [
        {"domain": "tenant.example"},
        {"audience": "https://api/"},
        {"client_id": "id"},
        {"client_secret": "secret"},
        {"token_store": object()},
        {"scope_matching": "non_strict"},
        {"organization_policy": "required"},
        {"organization_id": "org_1"},
        {"client_info": {"name": "wrapper", "version": "1.0.0"}},
    ],
)
def test_create_mcp_client_rejects_options_passed_with_api_client(option):
    with pytest.raises(ConfigurationError):
        create_mcp_client(api_client=StubApiClient(), **option)


@pytest.mark.parametrize("args", [{}, {"domain": "tenant.example"}, {"audience": "https://api/"}])
def test_create_mcp_client_needs_domain_and_audience_without_api_client(args):
    with pytest.raises(ConfigurationError, match="domain and audience"):
        create_mcp_client(**args)


def test_client_domain_is_none_in_multi_domain_mode():
    client = create_mcp_client(
        api_client=ApiClient(ApiClientOptions(domains=["a.example", "b.example"], audience="https://api/"))
    )

    assert client.domain is None
    assert client.audience == "https://api/"


def test_create_mcp_client_forwards_org_policy_to_core():
    client = create_mcp_client(
        "tenant.auth0.com",
        "https://api/",
        organization_policy="required",
        organization_id="org_abc",
    )
    assert client._api.options.organization_policy == "required"
    assert client._api.options.organization_id == "org_abc"


def test_create_mcp_client_forwards_client_credentials_to_core():
    client = create_mcp_client(
        "tenant.auth0.com", "https://api/", client_id="cid", client_secret="csecret"
    )
    assert client._api.options.client_id == "cid"
    assert client._api.options.client_secret == "csecret"


def test_create_mcp_client_passes_token_store_to_api_client_options():
    """create_mcp_client wires token_store into ApiClientOptions so core's cache is active."""

    class _MinimalStore(AbstractTokenStore):
        async def get(self, key):
            return None

        async def set(self, key, value):
            pass

        async def delete(self, key):
            pass

    store = _MinimalStore(secret="s" * 32)
    client = create_mcp_client("tenant.auth0.com", "https://api/", token_store=store)
    assert client._api.options.token_store is store


def test_create_mcp_client_forwards_scope_matching_to_core():
    class _MinimalIndexedStore(IndexedTokenStore):
        async def get(self, key):
            return None

        async def set(self, key, value):
            pass

        async def delete(self, key):
            pass

        async def add_index_member(self, index_key, member):
            pass

        async def list_index_members(self, index_key):
            return []

    client = create_mcp_client(
        "tenant.auth0.com",
        "https://api/",
        token_store=_MinimalIndexedStore(secret="s" * 32),
        scope_matching="non_strict",
    )
    assert client._api.options.scope_matching == "non_strict"


def test_create_mcp_client_reports_this_package_to_core():
    client = create_mcp_client("tenant.auth0.com", "https://api/")

    assert client._api.options.client_info == {
        "name": "auth0-ai-mcp",
        "version": importlib.metadata.version("auth0-ai-mcp"),
    }


def test_create_mcp_client_reports_the_wrapper_and_lists_this_package_in_env():
    client = create_mcp_client(
        "tenant.auth0.com",
        "https://api/",
        client_info={"name": "auth0-ai-fastmcp", "version": "1.2.3", "env": {"fastmcp": "3.0"}},
    )

    assert client._api.options.client_info == {
        "name": "auth0-ai-fastmcp",
        "version": "1.2.3",
        "env": {"fastmcp": "3.0", "auth0-ai-mcp": importlib.metadata.version("auth0-ai-mcp")},
    }


def test_create_mcp_client_wrapper_cannot_replace_this_packages_env_entry():
    client = create_mcp_client(
        "tenant.auth0.com",
        "https://api/",
        client_info={"name": "wrapper", "version": "1.0.0", "env": {"auth0-ai-mcp": "0.0.0"}},
    )

    assert client._api.options.client_info["env"]["auth0-ai-mcp"] == importlib.metadata.version("auth0-ai-mcp")


def test_client_info_version_is_unknown_when_the_package_is_not_installed(monkeypatch):
    def missing(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", missing)

    assert create_mcp_client("tenant.auth0.com", "https://api/")._api.options.client_info["version"] == "unknown"


@pytest.mark.parametrize(
    "client_info",
    [
        "wrapper",
        {"version": "1.0.0"},
        {"name": "wrapper", "version": "1.0.0", "env": "fastmcp"},
    ],
)
def test_create_mcp_client_rejects_malformed_client_info(client_info):
    with pytest.raises(ConfigurationError, match="client_info"):
        create_mcp_client("tenant.auth0.com", "https://api/", client_info=client_info)
