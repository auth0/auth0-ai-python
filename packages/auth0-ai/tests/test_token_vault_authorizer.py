"""
Tests for TokenVaultAuthorizer
"""
import pytest
from auth0_ai.authorizers.token_vault_authorizer import (
    TokenVaultAuthorizerBase, TokenVaultAuthorizerParams)


# Fixtures provide reusable test data/objects
@pytest.fixture
def mock_auth0_config():
    """Basic Auth0 configuration for testing"""
    return {
        "domain": "test.auth0.com",
        "client_id": "test_client_id",
        "client_secret": "test_client_secret",
    }


@pytest.fixture
def token_vault_params():
    """Sample TokenVaultAuthorizerParams with refresh token"""
    return TokenVaultAuthorizerParams(
        scopes=["read:data", "write:data"],
        connection="google-oauth2",
        refresh_token="test_refresh_token",
    )


@pytest.fixture
def token_vault_params_with_access_token():
    """Sample TokenVaultAuthorizerParams with access token"""
    return TokenVaultAuthorizerParams(
        scopes=["read:data"],
        connection="google-oauth2",
        access_token="test_access_token",
    )


class TestTokenVaultAuthorizerParams:
    """Tests for TokenVaultAuthorizerParams initialization"""

    def test_initialization_with_refresh_token(self, token_vault_params):
        """Test that params can be initialized with a refresh token"""
        assert token_vault_params.scopes == ["read:data", "write:data"]
        assert token_vault_params.connection == "google-oauth2"
        assert token_vault_params.refresh_token.value == "test_refresh_token"

    def test_initialization_with_access_token(self, token_vault_params_with_access_token):
        """Test that params can be initialized with an access token"""
        assert token_vault_params_with_access_token.scopes == ["read:data"]
        assert token_vault_params_with_access_token.connection == "google-oauth2"
        assert token_vault_params_with_access_token.access_token.value == "test_access_token"

    def test_must_provide_exactly_one_token_type(self, mock_auth0_config):
        """Test that initialization fails when both tokens are provided"""
        # Note: The validation happens in TokenVaultAuthorizerBase, not TokenVaultAuthorizerParams
        params = TokenVaultAuthorizerParams(
            scopes=["read:data"],
            connection="google-oauth2",
            refresh_token="refresh_token",
            access_token="access_token",
        )
        with pytest.raises(ValueError, match="Exactly one of refresh_token or access_token"):
            TokenVaultAuthorizerBase(params=params, config=mock_auth0_config)

    def test_must_provide_at_least_one_token_type(self, mock_auth0_config):
        """Test that initialization fails when no tokens are provided"""
        # Note: The validation happens in TokenVaultAuthorizerBase, not TokenVaultAuthorizerParams
        params = TokenVaultAuthorizerParams(
            scopes=["read:data"],
            connection="google-oauth2",
        )
        with pytest.raises(ValueError, match="Exactly one of refresh_token or access_token"):
            TokenVaultAuthorizerBase(params=params, config=mock_auth0_config)


class TestTokenVaultAuthorizerBase:
    """Tests for TokenVaultAuthorizerBase"""

    def test_initialization(self, token_vault_params, mock_auth0_config):
        """Test that the authorizer can be initialized"""
        authorizer = TokenVaultAuthorizerBase(
            params=token_vault_params,
            config=mock_auth0_config,
        )

        assert authorizer.params == token_vault_params
        assert authorizer.auth0["domain"] == "test.auth0.com"
        assert authorizer.auth0["client_id"] == "test_client_id"
        assert "client_secret" in authorizer.auth0

    @pytest.mark.asyncio
    async def test_get_refresh_token(self, token_vault_params, mock_auth0_config):
        """Test retrieving the refresh token"""
        authorizer = TokenVaultAuthorizerBase(
            params=token_vault_params,
            config=mock_auth0_config,
        )

        token = await authorizer.get_refresh_token()
        assert token == "test_refresh_token"

    @pytest.mark.asyncio
    async def test_get_refresh_token_handles_empty_string(self, mock_auth0_config):
        """Test that empty strings in refresh_token raise validation error during initialization"""
        params = TokenVaultAuthorizerParams(
            scopes=["read:data"],
            connection="google-oauth2",
            refresh_token="   ",  # Empty string with spaces
        )
        # Empty strings are normalized to None, which fails the "exactly one token" validation
        with pytest.raises(ValueError, match="Exactly one of refresh_token or access_token"):
            TokenVaultAuthorizerBase(params=params, config=mock_auth0_config)

    @pytest.mark.asyncio
    async def test_get_user_access_token(self, token_vault_params_with_access_token, mock_auth0_config):
        """Test retrieving the user access token"""
        authorizer = TokenVaultAuthorizerBase(
            params=token_vault_params_with_access_token,
            config=mock_auth0_config,
        )

        token = await authorizer.get_user_access_token()
        assert token == "test_access_token"


# Parametrized tests - run the same test with different inputs
@pytest.mark.parametrize("scopes,expected_count", [
    (["read:data"], 1),
    (["read:data", "write:data"], 2),
    (["read:data", "write:data", "delete:data"], 3),
])
def test_scopes_count(scopes, expected_count):
    """Test that different scope configurations work correctly"""
    params = TokenVaultAuthorizerParams(
        scopes=scopes,
        connection="google-oauth2",
        refresh_token="token",
    )
    assert len(params.scopes) == expected_count
