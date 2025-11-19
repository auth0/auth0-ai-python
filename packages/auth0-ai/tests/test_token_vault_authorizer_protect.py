"""
Tests for TokenVaultAuthorizer.protect() wrapper method

These tests focus on the protect wrapper's error handling, credential storage,
and ensuring proper cleanup when errors occur.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest
from auth0_ai.authorizers.token_vault_authorizer import (
    TokenVaultAuthorizerBase, TokenVaultAuthorizerParams)
from auth0_ai.credentials import TokenResponse
from auth0_ai.interrupts.auth0_interrupt import Auth0Interrupt
from auth0_ai.interrupts.token_vault_interrupt import TokenVaultError


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
def mock_credentials():
    """Sample token response credentials"""
    return TokenResponse(
        access_token="mock_access_token",
        expires_in=3600,
        scope=["read:data", "write:data"],
        token_type="Bearer",
    )


@pytest.fixture
def mock_store():
    """Mock store with AsyncMock methods"""
    store = MagicMock()
    store.get = AsyncMock()
    store.put = AsyncMock()
    store.delete = AsyncMock()
    return store


class TestProtectWrapper:
    """Tests for the protect() wrapper method"""

    @pytest.mark.asyncio
    async def test_protect_executes_function_successfully(
        self, token_vault_params, mock_auth0_config, mock_credentials, mock_store
    ):
        """Test that protect wrapper executes the wrapped function successfully"""
        # Setup
        token_vault_params.store = mock_store
        authorizer = TokenVaultAuthorizerBase(
            params=token_vault_params,
            config=mock_auth0_config,
        )

        # Mock the credentials store to return existing credentials
        authorizer.credentials_store.get = AsyncMock(
            return_value=mock_credentials)
        authorizer.credentials_store.put = AsyncMock()

        # Create a mock async function to wrap
        mock_execute = AsyncMock(return_value="success")

        # Create a simple context getter
        def get_context():
            return {
                "thread_id": "test_thread",
                "tool_call_id": "test_call_123",
                "tool_name": "test_tool"
            }

        # Wrap the function
        wrapped = authorizer.protect(get_context, mock_execute)

        # Execute
        result = await wrapped()

        # Assertions
        assert result == "success"
        mock_execute.assert_called_once()
        authorizer.credentials_store.get.assert_called_once()
        # Should not put new credentials since we got existing ones
        authorizer.credentials_store.put.assert_not_called()

    @pytest.mark.asyncio
    async def test_protect_fetches_and_stores_new_credentials(
        self, token_vault_params, mock_auth0_config, mock_credentials, mock_store
    ):
        """Test that protect fetches and stores new credentials when none exist"""
        # Setup
        token_vault_params.store = mock_store
        authorizer = TokenVaultAuthorizerBase(
            params=token_vault_params,
            config=mock_auth0_config,
        )

        # Mock the credentials store to return None (no existing credentials)
        authorizer.credentials_store.get = AsyncMock(return_value=None)
        authorizer.credentials_store.put = AsyncMock()

        # Mock get_access_token_impl to return new credentials
        authorizer.get_access_token_impl = AsyncMock(
            return_value=mock_credentials)

        # Mock validate_token to pass
        authorizer.validate_token = MagicMock()

        # Create a mock async function to wrap
        mock_execute = AsyncMock(return_value="success")

        def get_context():
            return {
                "thread_id": "test_thread",
                "tool_call_id": "test_call_456",
                "tool_name": "test_tool"
            }

        # Wrap and execute
        wrapped = authorizer.protect(get_context, mock_execute)
        result = await wrapped()

        # Assertions
        assert result == "success"
        authorizer.credentials_store.get.assert_called_once()
        authorizer.get_access_token_impl.assert_called_once()
        authorizer.validate_token.assert_called_once_with(mock_credentials)
        authorizer.credentials_store.put.assert_called_once()
        mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_protect_deletes_credentials_on_token_vault_error(
        self, token_vault_params, mock_auth0_config, mock_credentials, mock_store
    ):
        """
        CRITICAL TEST: Ensure credentials are deleted when TokenVaultError occurs.
        This test verifies the bug fix where delete wasn't awaited.
        """
        # Setup
        token_vault_params.store = mock_store
        authorizer = TokenVaultAuthorizerBase(
            params=token_vault_params,
            config=mock_auth0_config,
        )

        # Mock the credentials store
        authorizer.credentials_store.get = AsyncMock(
            return_value=mock_credentials)
        authorizer.credentials_store.put = AsyncMock()
        authorizer.credentials_store.delete = AsyncMock()

        # Create a mock function that raises TokenVaultError
        mock_execute = AsyncMock(side_effect=TokenVaultError("Invalid token"))

        def get_context():
            return {
                "thread_id": "test_thread",
                "tool_call_id": "test_call_456",
                "tool_name": "test_tool"
            }

        # Mock _handle_authorization_interrupts to not raise (so we can test the flow)
        authorizer._handle_authorization_interrupts = MagicMock()

        # Wrap and execute
        wrapped = authorizer.protect(get_context, mock_execute)
        await wrapped()

        # CRITICAL ASSERTIONS
        # Verify that delete was called
        authorizer.credentials_store.delete.assert_called_once()

        # Verify delete was awaited (AsyncMock tracks this)
        assert authorizer.credentials_store.delete.await_count == 1

        # Verify the interrupt handler was called
        authorizer._handle_authorization_interrupts.assert_called_once()

    @pytest.mark.asyncio
    async def test_protect_deletes_credentials_on_auth0_interrupt(
        self, token_vault_params, mock_auth0_config, mock_credentials, mock_store
    ):
        """Test that credentials are deleted when Auth0Interrupt occurs"""
        # Setup
        token_vault_params.store = mock_store
        authorizer = TokenVaultAuthorizerBase(
            params=token_vault_params,
            config=mock_auth0_config,
        )

        # Mock the credentials store
        authorizer.credentials_store.get = AsyncMock(
            return_value=mock_credentials)
        authorizer.credentials_store.delete = AsyncMock()

        # Create a mock function that raises Auth0Interrupt
        interrupt = Auth0Interrupt("Authorization required", "auth_required")
        mock_execute = AsyncMock(side_effect=interrupt)

        def get_context():
            return {
                "thread_id": "test_thread",
                "tool_call_id": "test_call_456",
                "tool_name": "test_tool"
            }

        authorizer._handle_authorization_interrupts = MagicMock()

        # Wrap and execute
        wrapped = authorizer.protect(get_context, mock_execute)
        await wrapped()

        # Assertions
        authorizer.credentials_store.delete.assert_called_once()
        assert authorizer.credentials_store.delete.await_count == 1
        authorizer._handle_authorization_interrupts.assert_called_once_with(
            interrupt)

    @pytest.mark.asyncio
    async def test_protect_uses_correct_namespace_for_credentials(
        self, token_vault_params, mock_auth0_config, mock_credentials, mock_store
    ):
        """Test that credentials are stored/retrieved with correct namespace"""
        # Setup
        token_vault_params.store = mock_store
        token_vault_params.credentials_context = "thread"  # Explicitly set context

        authorizer = TokenVaultAuthorizerBase(
            params=token_vault_params,
            config=mock_auth0_config,
        )

        # Mock the credentials store
        authorizer.credentials_store.get = AsyncMock(return_value=None)
        authorizer.credentials_store.put = AsyncMock()
        authorizer.get_access_token_impl = AsyncMock(
            return_value=mock_credentials)
        authorizer.validate_token = MagicMock()

        mock_execute = AsyncMock(return_value="success")

        def get_context():
            return {
                "thread_id": "test_thread_123",
                "tool_call_id": "call_456",
                "tool_name": "test_tool"
            }

        # Wrap and execute
        wrapped = authorizer.protect(get_context, mock_execute)
        await wrapped()

        # Verify that get and put were called with the namespace derived from context
        authorizer.credentials_store.get.assert_called_once()
        authorizer.credentials_store.put.assert_called_once()

        # Extract the namespace argument from the calls
        get_call_args = authorizer.credentials_store.get.call_args
        put_call_args = authorizer.credentials_store.put.call_args

        # Both should use the same namespace
        assert get_call_args[0][0] == put_call_args[0][0]

    @pytest.mark.asyncio
    async def test_protect_wraps_sync_functions(
        self, token_vault_params, mock_auth0_config, mock_credentials, mock_store
    ):
        """Test that protect can wrap synchronous functions (not just async)"""
        # Setup
        token_vault_params.store = mock_store
        authorizer = TokenVaultAuthorizerBase(
            params=token_vault_params,
            config=mock_auth0_config,
        )

        authorizer.credentials_store.get = AsyncMock(
            return_value=mock_credentials)

        # Create a SYNC function to wrap (note: not AsyncMock)
        mock_execute = MagicMock(return_value="sync_result")

        def get_context():
            return {
                "thread_id": "test_thread",
                "tool_call_id": "test_call_456",
                "tool_name": "test_tool"
            }

        # Wrap and execute
        wrapped = authorizer.protect(get_context, mock_execute)
        result = await wrapped()  # The wrapper is async even if the function isn't

        # Assertions
        assert result == "sync_result"
        mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_protect_passes_args_and_kwargs_to_wrapped_function(
        self, token_vault_params, mock_auth0_config, mock_credentials, mock_store
    ):
        """Test that protect passes through arguments to the wrapped function"""
        # Setup
        token_vault_params.store = mock_store
        authorizer = TokenVaultAuthorizerBase(
            params=token_vault_params,
            config=mock_auth0_config,
        )

        authorizer.credentials_store.get = AsyncMock(
            return_value=mock_credentials)

        mock_execute = AsyncMock(return_value="success")

        def get_context(*args, **kwargs):
            return {
                "thread_id": "test_thread",
                "tool_call_id": "test_call_789",
                "tool_name": "test_tool"
            }

        # Wrap and execute with args and kwargs
        wrapped = authorizer.protect(get_context, mock_execute)
        await wrapped("arg1", "arg2", key1="value1", key2="value2")

        # Verify the wrapped function received all arguments
        mock_execute.assert_called_once_with(
            "arg1", "arg2", key1="value1", key2="value2")

    @pytest.mark.asyncio
    async def test_protect_local_storage_cleanup_after_execution(
        self, token_vault_params, mock_auth0_config, mock_credentials, mock_store
    ):
        """Test that local storage is properly cleaned up after execution"""
        # Setup
        token_vault_params.store = mock_store
        authorizer = TokenVaultAuthorizerBase(
            params=token_vault_params,
            config=mock_auth0_config,
        )

        authorizer.credentials_store.get = AsyncMock(
            return_value=mock_credentials)

        mock_execute = AsyncMock(return_value="success")

        def get_context():
            return {
                "thread_id": "test_thread",
                "tool_call_id": "test_call_456",
                "tool_name": "test_tool"
            }

        # Wrap and execute
        wrapped = authorizer.protect(get_context, mock_execute)
        await wrapped()

        # Try to access local storage outside the context - should fail
        from auth0_ai.authorizers.token_vault_authorizer import \
            _get_local_storage

        with pytest.raises(RuntimeError, match="must be wrapped with the with_token_vault"):
            _get_local_storage()

    @pytest.mark.asyncio
    async def test_protect_prevents_nested_tool_calls(
        self, token_vault_params, mock_auth0_config, mock_credentials, mock_store
    ):
        """Test that nested tool calls are prevented"""
        # Setup
        token_vault_params.store = mock_store
        authorizer = TokenVaultAuthorizerBase(
            params=token_vault_params,
            config=mock_auth0_config,
        )

        authorizer.credentials_store.get = AsyncMock(
            return_value=mock_credentials)

        # Create a nested function that tries to call another protected function
        async def nested_execute():
            # This should fail because we're already in a protected context
            def inner_context():
                return {
                    "thread_id": "inner_thread",
                    "tool_call_id": "inner_call_999",
                    "tool_name": "inner_tool"
                }

            inner_wrapped = authorizer.protect(inner_context, AsyncMock())
            await inner_wrapped()

        def get_context():
            return {
                "thread_id": "outer_thread",
                "tool_call_id": "outer_call_123",
                "tool_name": "outer_tool"
            }

        wrapped = authorizer.protect(get_context, nested_execute)

        # This should raise RuntimeError about nesting
        with pytest.raises(RuntimeError, match="Cannot nest tool calls"):
            await wrapped()

    @pytest.mark.asyncio
    async def test_protect_credential_deletion_with_correct_namespace(
        self, token_vault_params, mock_auth0_config, mock_credentials, mock_store
    ):
        """
        Test that credentials are deleted from the correct namespace.
        This is critical for multi-tenant or multi-context scenarios.
        """
        # Setup
        token_vault_params.store = mock_store
        authorizer = TokenVaultAuthorizerBase(
            params=token_vault_params,
            config=mock_auth0_config,
        )

        # Mock the credentials store
        authorizer.credentials_store.get = AsyncMock(
            return_value=mock_credentials)
        authorizer.credentials_store.delete = AsyncMock()

        # Create a function that raises TokenVaultError
        mock_execute = AsyncMock(side_effect=TokenVaultError("Invalid token"))

        context_data = {
            "thread_id": "specific_thread_789",
            "tool_call_id": "call_999",
            "tool_name": "specific_tool"
        }

        def get_context():
            return context_data

        authorizer._handle_authorization_interrupts = MagicMock()

        # Wrap and execute
        wrapped = authorizer.protect(get_context, mock_execute)
        await wrapped()

        # Verify delete was called
        assert authorizer.credentials_store.delete.await_count == 1

        # Verify the namespace used for deletion matches what was used for get
        get_namespace = authorizer.credentials_store.get.call_args[0][0]
        delete_namespace = authorizer.credentials_store.delete.call_args[0][0]

        assert get_namespace == delete_namespace, "Delete should use the same namespace as get"


class TestProtectWithDifferentCredentialContexts:
    """Test protect with different credential_context settings"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("context_type", ["thread", "agent", "tool", "tool-call"])
    async def test_protect_with_different_contexts(
        self, context_type, mock_auth0_config, mock_store
    ):
        """Test that protect works with different credential_context settings"""
        params = TokenVaultAuthorizerParams(
            scopes=["read:data"],
            connection="google-oauth2",
            refresh_token="test_token",
            credentials_context=context_type,
            store=mock_store,
        )

        authorizer = TokenVaultAuthorizerBase(
            params=params, config=mock_auth0_config)

        mock_credentials = TokenResponse(
            access_token="mock_token",
            expires_in=3600,
            scope=["read:data"],
            token_type="Bearer",
        )

        authorizer.credentials_store.get = AsyncMock(
            return_value=mock_credentials)
        mock_execute = AsyncMock(return_value="success")

        def get_context():
            return {
                "thread_id": "thread_123",
                "tool_call_id": "call_456",
                "tool_name": "test_tool",
            }

        wrapped = authorizer.protect(get_context, mock_execute)
        result = await wrapped()

        assert result == "success"
        authorizer.credentials_store.get.assert_called_once()
        authorizer.credentials_store.get.assert_called_once()
