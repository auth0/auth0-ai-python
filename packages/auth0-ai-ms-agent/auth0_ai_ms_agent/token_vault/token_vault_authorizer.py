from agent_framework import FunctionTool

from auth0_ai.authorizers.token_vault_authorizer import TokenVaultAuthorizerBase
from auth0_ai_ms_agent.utils.tool_wrapper import tool_wrapper

class TokenVaultAuthorizer(TokenVaultAuthorizerBase):
    def authorizer(self):
        def wrap_tool(tool: FunctionTool) -> FunctionTool:
            return tool_wrapper(tool, self.protect)

        return wrap_tool
