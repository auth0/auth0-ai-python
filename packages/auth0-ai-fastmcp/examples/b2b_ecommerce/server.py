"""B2B ecommerce MCP server on Prefect FastMCP, secured with Auth0 through auth0-ai-fastmcp."""

import logging
import os

from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp_features import CallerAuditMiddleware, register_features
from token_store import InMemoryIndexedTokenStore, InMemoryTokenStore

from auth0_ai_fastmcp import Auth0FastMCP, Auth0FastMCPOptions

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(name)s %(levelname)s %(message)s")

DOMAIN = os.environ["AUTH0_DOMAIN"]
RESOURCE_URL = os.environ["MCP_RESOURCE_URL"]
ORGANIZATION_ID = os.environ.get("AUTH0_ORGANIZATION_ID") or None
SCOPE_MATCHING = os.environ.get("SCOPE_MATCHING", "strict")
TOKEN_STORE_SECRET = os.environ["TOKEN_STORE_SECRET"]
OBO_CLIENT_ID = os.environ.get("OBO_CLIENT_ID")
OBO_CLIENT_SECRET = os.environ.get("OBO_CLIENT_SECRET")

# Fail at startup, otherwise the first tool call fails with a generic error.
if not OBO_CLIENT_ID or not OBO_CLIENT_SECRET:
    raise SystemExit("Set OBO_CLIENT_ID and OBO_CLIENT_SECRET in .env, see step 2 of the README.")

# Advertised in the RFC 9728 metadata so the MCP client requests them at login.
TOOL_SCOPES = [
    "tool:cancel_and_refund_order",
    "tool:fulfill_order",
    "tool:order_status_report",
    "tool:update_customer_and_notify",
    "tool:sales_analytics_report",
]

# non_strict needs an index-backed store. strict works with the plain store.
store_class = InMemoryIndexedTokenStore if SCOPE_MATCHING == "non_strict" else InMemoryTokenStore
store = store_class(secret=TOKEN_STORE_SECRET)

# FastMCP appends /mcp to resource_url, and the audience defaults to that URL.
auth0 = Auth0FastMCP(
    Auth0FastMCPOptions(
        domain=DOMAIN,
        resource_url=RESOURCE_URL,
        tool_scopes=TOOL_SCOPES,
        client_id=OBO_CLIENT_ID,
        client_secret=OBO_CLIENT_SECRET,
        token_store=store,
        scope_matching=SCOPE_MATCHING,
        organization_policy="required" if ORGANIZATION_ID else "allow",
        organization_id=ORGANIZATION_ID,
    )
)

mcp = FastMCP(name="B2B Ecommerce MCP Server", auth=auth0.provider)
mcp.add_middleware(auth0.middleware)
mcp.add_middleware(CallerAuditMiddleware())

# Imported here because tools.py reads its audience variables at import time.
from tools import register_tools  # noqa: E402

register_tools(mcp)
register_features(mcp)


if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=3002)
