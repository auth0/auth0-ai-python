"""Auth0 AI for Microsoft Agent Framework.

Provides decorators to secure MS Agent tools using Auth0 authorization flows.
"""

from typing import Callable, Optional
from agent_framework import FunctionTool
from auth0_ai.authorizers.token_vault_authorizer import TokenVaultAuthorizerParams
from auth0_ai.authorizers.types import Auth0ClientParams
from auth0_ai_ms_agent.token_vault.token_vault_authorizer import TokenVaultAuthorizer


class Auth0AI:
    """Provides decorators to secure MS Agent tools using Auth0 authorization flows."""

    def __init__(self, auth0: Optional[Auth0ClientParams] = None):
        """Initializes the Auth0AI instance.

        Args:
            auth0 (Optional[Auth0ClientParams]): Parameters for the Auth0 client.
                If not provided, values will be automatically read from environment
                variables: `AUTH0_DOMAIN`, `AUTH0_CLIENT_ID`, and `AUTH0_CLIENT_SECRET`.
        """
        self.auth0 = auth0

    def with_token_vault(self, **params: TokenVaultAuthorizerParams) -> Callable[[FunctionTool], FunctionTool]:
        """Enables a tool to obtain an access token from a Token Vault identity provider (e.g., Google, Azure AD).

        The token can then be used within the tool to call third-party APIs on behalf of the user.

        Args:
            **params: Parameters defined in `TokenVaultAuthorizerParams`.

        Returns:
            Callable[[FunctionTool], FunctionTool]: A decorator to wrap an MS Agent FunctionTool.

        Example:
            ```python
            from auth0_ai_ms_agent.auth0_ai import Auth0AI
            from auth0_ai_ms_agent.token_vault import get_credentials_from_token_vault
            from agent_framework import FunctionTool
            from datetime import datetime

            auth0_ai = Auth0AI()

            with_google_calendar_access = auth0_ai.with_token_vault(
                connection="google-oauth2",
                scopes=["openid", "https://www.googleapis.com/auth/calendar.freebusy"],
                refresh_token=lambda *_args, **_kwargs: session["user"]["refresh_token"],
            )

            def tool_function(date: datetime):
                credentials = get_credentials_from_token_vault()
                # Call Google API using credentials["access_token"]

            check_calendar_tool = with_google_calendar_access(
                FunctionTool(
                    name="check_user_calendar",
                    description="Use this function to check if the user is available on a certain date and time",
                    func=tool_function,
                )
            )

            # Pass session when running the agent:
            # result = await agent.run(
            #     "Am I free on Friday at 10am?",
            #     options={"additional_function_arguments": {"session": session}},
            # )
            ```
        """
        authorizer = TokenVaultAuthorizer(
            TokenVaultAuthorizerParams(**params), self.auth0
        )
        return authorizer.authorizer()
