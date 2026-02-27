from abc import ABC
from agent_framework import FunctionTool

from auth0_ai.authorizers.token_vault_authorizer import (
    TokenVaultAuthorizerBase,
    TokenVaultAuthorizerParams
)
from auth0_ai.authorizers.types import Auth0ClientParams
from auth0_ai_ms_agent.utils.tool_wrapper import tool_wrapper

class TokenVaultAuthorizer(TokenVaultAuthorizerBase, ABC):
    def __init__(
        self,
        params: TokenVaultAuthorizerParams,
        auth0: Auth0ClientParams = None,
    ):
        super().__init__(params, auth0)

    def authorizer(self):
        def wrap_tool(tool: FunctionTool) -> FunctionTool:
            return tool_wrapper(tool, self.protect)

        return wrap_tool