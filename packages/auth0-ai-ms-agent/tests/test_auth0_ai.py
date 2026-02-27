"""
Tests for auth0_ai_ms_agent.auth0_ai.Auth0AI

Exercises the public entry point Auth0AI.with_token_vault() end-to-end,
mocking only at the actual HTTP boundary (get_access_token_impl) so that
the core SDK's protect() logic runs for real.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from agent_framework import FunctionTool
from auth0_ai.authorizers.token_vault_authorizer import (
    TokenVaultAuthorizerBase,
    _get_local_storage,
)
from auth0_ai.credentials import TokenResponse
from auth0_ai.interrupts.token_vault_interrupt import TokenVaultInterrupt

from auth0_ai_ms_agent.auth0_ai import Auth0AI

# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------

_AUTH0_CONFIG = {
    "domain": "test.auth0.com",
    "client_id": "test_client_id",
    "client_secret": "test_client_secret",
}

_TOKEN_VAULT_PARAMS = dict(
    connection="google-oauth2",
    scopes=["openid"],
    refresh_token="test_refresh_token",
)

# Credentials returned by the mocked HTTP layer for the "authorization passes" path.
_MOCK_CREDENTIALS: TokenResponse = {
    "access_token": "test-access-token",
    "expires_in": 3600,
    "scope": ["openid"],
    "token_type": "Bearer",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_session(session_id: str = "test-session-id") -> MagicMock:
    session = MagicMock()
    session.session_id = session_id
    session.state = {}
    return session


def _passing_mock():
    """AsyncMock that simulates a successful token exchange."""
    return AsyncMock(return_value=_MOCK_CREDENTIALS)


def _failing_mock():
    """AsyncMock that returns None, causing validate_token() to raise TokenVaultInterrupt."""
    return AsyncMock(return_value=None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWithTokenVault:

    def _auth0_ai(self) -> Auth0AI:
        return Auth0AI(auth0=_AUTH0_CONFIG)

    # --- Interface / contract ---

    def test_returns_callable_decorator(self):
        """with_token_vault() returns a callable decorator."""
        decorator = self._auth0_ai().with_token_vault(**_TOKEN_VAULT_PARAMS)
        assert callable(decorator)

    def test_decorator_returns_function_tool(self):
        """Decorator applied to a FunctionTool returns a FunctionTool."""
        decorator = self._auth0_ai().with_token_vault(**_TOKEN_VAULT_PARAMS)
        wrapped = decorator(FunctionTool(func=lambda: None, name="tool", description="Tool"))
        assert isinstance(wrapped, FunctionTool)

    def test_returned_function_tool_preserves_name_and_description(self):
        """Returned FunctionTool keeps the original tool's name and description."""
        decorator = self._auth0_ai().with_token_vault(**_TOKEN_VAULT_PARAMS)
        wrapped = decorator(
            FunctionTool(func=lambda: None, name="my_tool", description="My description")
        )
        assert wrapped.name == "my_tool"
        assert wrapped.description == "My description"

    def test_returned_function_tool_preserves_configuration(self):
        """Returned FunctionTool preserves approval and invocation settings."""
        decorator = self._auth0_ai().with_token_vault(**_TOKEN_VAULT_PARAMS)
        original = FunctionTool(
            func=lambda: None,
            name="tool",
            description="Tool",
            approval_mode="always_require",
            max_invocations=2,
            max_invocation_exceptions=3,
            additional_properties={"foo": "bar"},
        )
        wrapped = decorator(original)

        assert wrapped.approval_mode == original.approval_mode
        assert wrapped.max_invocations == original.max_invocations
        assert wrapped.max_invocation_exceptions == original.max_invocation_exceptions
        assert wrapped.additional_properties == original.additional_properties

    def test_returned_function_tool_preserves_schema_supplied_input_model(self):
        """Schema-supplied input models remain intact after wrapping."""
        decorator = self._auth0_ai().with_token_vault(**_TOKEN_VAULT_PARAMS)
        schema = {
            "type": "object",
            "properties": {"q": {"type": "string"}},
            "required": ["q"],
        }
        original = FunctionTool(
            func=lambda q: q,
            name="tool",
            description="Tool",
            input_model=schema,
        )
        wrapped = decorator(original)

        assert wrapped.parameters() == original.parameters()

    @pytest.mark.asyncio
    async def test_get_context_is_invoked_on_execution(self):
        """get_context must be called so the authorizer can resolve the credential namespace."""
        captured_context = []

        def tool_fn():
            captured_context.append(_get_local_storage()["context"])
            return "result"

        wrapped = self._auth0_ai().with_token_vault(**_TOKEN_VAULT_PARAMS)(
            FunctionTool(func=tool_fn, name="my_tool", description="Tool")
        )

        with patch.object(TokenVaultAuthorizerBase, "get_access_token_impl", _passing_mock()):
            await wrapped.func(session=_mock_session())

        assert len(captured_context) == 1
        ctx = captured_context[0]
        assert ctx["tool_name"] == "my_tool"
        assert "thread_id" in ctx
        assert "tool_call_id" in ctx

    @pytest.mark.asyncio
    async def test_raises_runtime_error_when_session_is_not_provided(self):
        """Raises RuntimeError if no session is passed — session is required to record tool state."""
        wrapped = self._auth0_ai().with_token_vault(**_TOKEN_VAULT_PARAMS)(
            FunctionTool(func=lambda: None, name="my_tool", description="Tool")
        )

        with pytest.raises(RuntimeError, match="my_tool"):
            await wrapped.func()

    # --- Behaviour ---

    @pytest.mark.asyncio
    async def test_wrapped_sync_function_executes_when_authorization_passes(self):
        """Wrapped sync function executes when authorization passes."""
        calls = []

        def sync_func():
            calls.append("executed")
            return "sync_result"

        wrapped = self._auth0_ai().with_token_vault(**_TOKEN_VAULT_PARAMS)(
            FunctionTool(func=sync_func, name="tool", description="Tool")
        )

        with patch.object(TokenVaultAuthorizerBase, "get_access_token_impl", _passing_mock()):
            result = await wrapped.func(session=_mock_session())

        assert result == "sync_result"
        assert calls == ["executed"]

    @pytest.mark.asyncio
    async def test_wrapped_async_function_executes_when_authorization_passes(self):
        """Wrapped async function executes when authorization passes."""
        calls = []

        async def async_func():
            calls.append("executed")
            return "async_result"

        wrapped = self._auth0_ai().with_token_vault(**_TOKEN_VAULT_PARAMS)(
            FunctionTool(func=async_func, name="tool", description="Tool")
        )

        with patch.object(TokenVaultAuthorizerBase, "get_access_token_impl", _passing_mock()):
            result = await wrapped.func(session=_mock_session())

        assert result == "async_result"
        assert calls == ["executed"]

    @pytest.mark.asyncio
    async def test_wrapped_function_does_not_execute_when_authorization_fails(self):
        """Wrapped function does not execute when authorization fails."""
        calls = []

        def guarded_func():
            calls.append("executed")
            return "result"

        wrapped = self._auth0_ai().with_token_vault(**_TOKEN_VAULT_PARAMS)(
            FunctionTool(func=guarded_func, name="tool", description="Tool")
        )

        with patch.object(TokenVaultAuthorizerBase, "get_access_token_impl", _failing_mock()):
            with pytest.raises(TokenVaultInterrupt):
                await wrapped.func(session=_mock_session())

        assert calls == [], "Original function must not be invoked when authorization fails"

    @pytest.mark.asyncio
    async def test_raises_token_vault_interrupt_on_authorization_failure(self):
        """TokenVaultInterrupt raised by the authorizer propagates to the caller."""
        wrapped = self._auth0_ai().with_token_vault(**_TOKEN_VAULT_PARAMS)(
            FunctionTool(func=lambda: None, name="tool", description="Tool")
        )

        with patch.object(TokenVaultAuthorizerBase, "get_access_token_impl", _failing_mock()):
            with pytest.raises(TokenVaultInterrupt):
                await wrapped.func(session=_mock_session())

    @pytest.mark.asyncio
    async def test_session_is_marked_as_interrupted_on_token_vault_interrupt(self):
        """When TokenVaultInterrupt is raised, session.state['pending_interrupt'] is set."""
        session = _mock_session()

        wrapped = self._auth0_ai().with_token_vault(**_TOKEN_VAULT_PARAMS)(
            FunctionTool(func=lambda: None, name="tool", description="Tool")
        )

        with patch.object(TokenVaultAuthorizerBase, "get_access_token_impl", _failing_mock()):
            with pytest.raises(TokenVaultInterrupt):
                await wrapped.func(session=session)

        assert isinstance(session.state["pending_interrupt"], TokenVaultInterrupt)

    @pytest.mark.asyncio
    async def test_session_is_not_marked_as_interrupted_when_authorization_passes(self):
        """When authorization passes, session.state is not populated with pending_interrupt."""
        session = _mock_session()

        wrapped = self._auth0_ai().with_token_vault(**_TOKEN_VAULT_PARAMS)(
            FunctionTool(func=lambda: None, name="tool", description="Tool")
        )

        with patch.object(TokenVaultAuthorizerBase, "get_access_token_impl", _passing_mock()):
            await wrapped.func(session=session)

        assert "pending_interrupt" not in session.state

    @pytest.mark.asyncio
    async def test_framework_kwargs_are_stripped_before_calling_original_function(self):
        """Framework-injected kwargs are removed before the original function is called."""
        received_kwargs: dict = {}

        def capturing_func(**kwargs):
            received_kwargs.update(kwargs)
            return "result"

        wrapped = self._auth0_ai().with_token_vault(**_TOKEN_VAULT_PARAMS)(
            FunctionTool(func=capturing_func, name="tool", description="Tool")
        )

        with patch.object(TokenVaultAuthorizerBase, "get_access_token_impl", _passing_mock()):
            await wrapped.func(
                session=_mock_session(),
                chat_options={"model": "gpt-4"},
                conversation_id="conv-123",
                user_arg="keep_me",
            )

        assert "session" not in received_kwargs
        assert "chat_options" not in received_kwargs
        assert "conversation_id" not in received_kwargs
        assert received_kwargs.get("user_arg") == "keep_me"

    @pytest.mark.asyncio
    async def test_non_token_vault_exceptions_propagate_unchanged(self):
        """Arbitrary exceptions from the tool function propagate to the caller unchanged."""
        class CustomError(Exception):
            pass

        def failing_func():
            raise CustomError("something went wrong")

        session = _mock_session()

        wrapped = self._auth0_ai().with_token_vault(**_TOKEN_VAULT_PARAMS)(
            FunctionTool(func=failing_func, name="tool", description="Tool")
        )

        with patch.object(TokenVaultAuthorizerBase, "get_access_token_impl", _passing_mock()):
            with pytest.raises(CustomError, match="something went wrong"):
                await wrapped.func(session=session)

        assert "pending_interrupt" not in session.state
