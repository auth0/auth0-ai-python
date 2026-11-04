"""FastMCP features that sit on top of the Auth0 request context: a middleware, a resource and a prompt."""

import logging

from auth0_ai_mcp import get_caller_principal, require_caller_principal
from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext

from auth0_ai_fastmcp import require_scopes

logger = logging.getLogger("audit")


class CallerAuditMiddleware(Middleware):
    """Logs who called each tool. Add it after auth0.middleware so the caller is already set."""

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        principal = get_caller_principal()
        logger.info("tool=%s caller=%s", context.message.name, principal.sub if principal else None)
        return await call_next(context)


def register_features(mcp: FastMCP) -> None:
    @mcp.tool(
        name="whoami",
        description="Returns the caller's subject, scopes and organization from the verified token.",
        annotations={"readOnlyHint": True},
    )
    async def whoami() -> dict:
        principal = require_caller_principal()
        return {
            "sub": principal.sub,
            "scopes": principal.scopes,
            "org_id": principal.org_id,
            "expires_at": principal.expires_at,
        }

    @mcp.resource("store://catalog/summary")
    async def catalog_summary() -> str:
        """Catalog summary for callers who may run order status reports."""
        require_scopes(get_caller_principal(), "tool:order_status_report")
        return "12 product lines across 3 warehouses (demo data)"

    @mcp.prompt
    async def fulfillment_checklist(order_id: str) -> str:
        """Checklist prompt for callers who may fulfill orders."""
        require_scopes(get_caller_principal(), "tool:fulfill_order")
        return f"Confirm stock, create the shipment and notify the customer for order {order_id}."
