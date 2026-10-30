"""B2B ecommerce MCP server secured with Auth0 through the auth0-ai-mcp ASGI middleware.

One incoming user token becomes a narrower token per downstream service through
On-Behalf-Of (OBO). Business logic is stubbed, the auth is real.
"""

import logging
import os

import uvicorn
from dotenv import load_dotenv
from mcp.server.mcpserver import MCPServer
from token_store import InMemoryIndexedTokenStore, InMemoryTokenStore

from auth0_ai_mcp import create_mcp_client
from auth0_ai_mcp.middleware import Auth0AsgiMiddleware

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")

DOMAIN = os.environ["AUTH0_DOMAIN"]
AUDIENCE = os.environ["AUTH0_AUDIENCE"]
ORGANIZATION_ID = os.environ.get("AUTH0_ORGANIZATION_ID") or None
SCOPE_MATCHING = os.environ.get("SCOPE_MATCHING", "strict")
TOKEN_STORE_SECRET = os.environ["TOKEN_STORE_SECRET"]

# Advertised in the RFC 9728 metadata so the MCP client requests them at login.
TOOL_SCOPES = [
    "tool:cancel_and_refund_order",
    "tool:fulfill_order",
    "tool:order_status_report",
    "tool:update_customer_and_notify",
    "tool:sales_analytics_report",
]

# non_strict needs an index-backed store. Strict works with the plain store.
store_class = InMemoryIndexedTokenStore if SCOPE_MATCHING == "non_strict" else InMemoryTokenStore
store = store_class(secret=TOKEN_STORE_SECRET)

# Setting AUTH0_ORGANIZATION_ID switches the server to organization-required mode
# and pins accepted tokens to that org. Unset leaves the default allow mode.
mcp_client = create_mcp_client(
    DOMAIN,
    AUDIENCE,
    client_id=os.environ["OBO_CLIENT_ID"],
    client_secret=os.environ["OBO_CLIENT_SECRET"],
    token_store=store,
    scope_matching=SCOPE_MATCHING,
    organization_policy="required" if ORGANIZATION_ID else "allow",
    organization_id=ORGANIZATION_ID,
)

mcp = MCPServer(name="B2B Ecommerce MCP Server")

from tools import register_tools  # noqa: E402

register_tools(mcp)

# Wrap the streamable-HTTP app so every request is verified before it reaches a tool.
app = Auth0AsgiMiddleware(
    mcp.streamable_http_app(host="127.0.0.1"),
    mcp_client=mcp_client,
    scopes_supported=TOOL_SCOPES,
)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=3002)
